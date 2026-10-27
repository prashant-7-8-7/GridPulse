import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import numpy as np
import pandas as pd
from gridpulse.config import ROOT
from gridpulse.schema import validate, read_csv, features, WEATHER
from gridpulse.controller import transition
from gridpulse.battery import Battery, simulate
from gridpulse.quickml import QuickMLClient, QuickMLError


def window():
    return pd.DataFrame({"timestamp": pd.date_range("2026-10-27", periods=24, freq="h").strftime("%Y-%m-%d %H:%M:%S"),
                         "ambient_temp_c": 29., "humidity_pct": 50., "solar_irradiance_wm2": 100.})


MEDIANS = dict(zip(WEATHER, [25., 55., 100.]))


class ControllerTests(unittest.TestCase):
    def test_thresholds_and_inclusive_window(self):
        cases = [("17:00:00",160,"main_grid",False),("17:00:00",160.00001,"renewable_storage",False),
                 ("18:00:00",20,"renewable_storage",False),("22:00:00",20,"renewable_storage",False),
                 ("23:00:00",160,"main_grid",False),("10:00:00",199.99999,"renewable_storage",False),
                 ("10:00:00",200,"renewable_storage",True),("22:00:00",201,"renewable_storage",True)]
        for time,value,mode,alert in cases:
            with self.subTest(time=time,value=value):
                signal=transition("2026-10-27 "+time,value)
                self.assertEqual(signal["grid_mode"],mode);self.assertEqual(signal["critical_overload"],alert)

    def test_invalid_demand(self):
        for value in [np.inf,np.nan,-1]:
            with self.assertRaises(ValueError):transition("2026-10-27 12:00:00",value)


class InputTests(unittest.TestCase):
    def test_valid_window_and_feature_consistency(self):
        clean,_=validate(window(),MEDIANS,hourly_window=True)
        self.assertEqual(len(clean),24)
        self.assertTrue(features(clean.iloc[[3]]).reset_index(drop=True).equals(features(clean).iloc[[3]].reset_index(drop=True)))

    def test_missing_column(self):
        with self.assertRaisesRegex(ValueError,"Missing columns"):validate(window().drop(columns=WEATHER[0]),MEDIANS)

    def test_missing_values_use_training_not_future_median(self):
        frame=window();frame.loc[0,WEATHER[0]]=np.nan;frame.loc[1:,WEATHER[0]]=60
        clean,warnings=validate(frame,MEDIANS)
        self.assertEqual(clean.loc[0,WEATHER[0]],25);self.assertEqual(len(warnings),1)

    def test_entire_missing_column_is_supported(self):
        frame=window();frame[WEATHER[1]]=np.nan
        clean,_=validate(frame,MEDIANS);self.assertTrue(clean[WEATHER[1]].eq(55).all())

    def test_text_infinity_and_ranges(self):
        for column,value in [("ambient_temp_c","oops"),("humidity_pct",101),("solar_irradiance_wm2",-1),("ambient_temp_c",np.inf)]:
            frame=window();frame[column]=frame[column].astype(object);frame.loc[0,column]=value
            with self.subTest(column=column,value=value),self.assertRaises(ValueError):validate(frame,MEDIANS)

    def test_duplicate_unsorted_gap_and_short_window(self):
        for change in [lambda f:f.iloc[:-1],lambda f:f.iloc[::-1],lambda f:pd.concat([f.iloc[:23],f.iloc[[0]]]),lambda f:f.assign(timestamp=f.timestamp.str.replace("00:00:00","00:30:00",regex=False))]:
            with self.assertRaises(ValueError):validate(change(window()),MEDIANS,hourly_window=True)

    def test_bad_timestamp(self):
        frame=window();frame.loc[0,"timestamp"]="2026/10/27 00:00:00"
        with self.assertRaises(ValueError):validate(frame,MEDIANS)

    def test_duplicate_headers_and_wrong_width(self):
        for text in ["timestamp,timestamp\na,b\n","a,b\n1,2,3\n",""]:
            with self.assertRaises(ValueError):read_csv(text)

    def test_target_does_not_become_feature(self):
        frame=window();frame["target_demand_kw"]=100000
        clean,_=validate(frame,MEDIANS)
        self.assertNotIn("target_demand_kw",features(clean))


class BatteryTests(unittest.TestCase):
    def test_discharge_efficiency_and_shortfall(self):
        row={"timestamp":"2026-10-27 18:00:00","target_demand_kw":200.,"solar_irradiance_wm2":0.,**transition("2026-10-27 18:00:00",200.)}
        out=simulate([row],Battery(capacity_kwh=100,initial_soc_pct=100,reserve_soc_pct=20,efficiency=.9))[0]
        self.assertAlmostEqual(out["battery_delivered_kwh"],72);self.assertAlmostEqual(out["unserved_energy_kwh"],128)
        self.assertEqual(out["soc_end_pct"],20);self.assertTrue(out["battery_shortfall"])
        self.assertEqual(out["grid_mode"],"renewable_storage");self.assertTrue(out["critical_overload"])

    def test_charge_capacity_and_inverter_bound(self):
        row={"target_demand_kw":20.,"solar_irradiance_wm2":1000.,"grid_mode":"main_grid"}
        out=simulate([row]*24,Battery(capacity_kwh=100,initial_soc_pct=90,reserve_soc_pct=20,solar_peak_kw=200))[0]
        self.assertEqual(out["soc_end_pct"],100)
        row["grid_mode"]="renewable_storage";row["target_demand_kw"]=400;row["solar_irradiance_wm2"]=0
        out=simulate([row],Battery(inverter_limit_kw=50))[0];self.assertEqual(out["battery_delivered_kwh"],50)

    def test_bad_settings(self):
        for value in [{"capacity_kwh":0},{"initial_soc_pct":10,"reserve_soc_pct":20},{"efficiency":np.nan},{"unexpected":1}]:
            with self.assertRaises(ValueError):Battery.from_dict(value)


class QuickMLTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{"QUICKML_ENDPOINT_URL":"https://api.catalyst.zoho.in/example",
           "QUICKML_ENDPOINT_KEY":"secret-key","QUICKML_ORG_ID":"123","QUICKML_ACCESS_TOKEN":"secret-token",
           "QUICKML_REFRESH_TOKEN":"","QUICKML_REQUEST_MODE":"single","QUICKML_REQUEST_KEY":"",
           "QUICKML_RESPONSE_PATH":"result","QUICKML_BATCH_SIZE":"2"})
        self.env.start()

    def tearDown(self):self.env.stop()

    def test_single_row_shape_headers_and_order(self):
        client=QuickMLClient();calls=[]
        def send(request,operation):
            calls.append(request)
            return {"result":[{"prediction":json.loads(request.data)["hour"]+100}]}
        with patch.object(client,"_send",side_effect=send):
            self.assertEqual(client.predict([{"hour":8},{"hour":4}]),[108,104])
        self.assertEqual(calls[0].get_header("Authorization"),"Zoho-oauthtoken secret-token")
        self.assertEqual(calls[0].get_header("X-quickml-endpoint-key"),"secret-key")

    def test_batch_chunks_and_starter_response_shape(self):
        with patch.dict(os.environ,{"QUICKML_REQUEST_MODE":"batch","QUICKML_REQUEST_KEY":"data","QUICKML_RESPONSE_PATH":"predictions"}):
            client=QuickMLClient();sizes=[]
            def send(request,operation):
                records=json.loads(request.data)["data"];sizes.append(len(records));return {"predictions":[r["v"] for r in records]}
            with patch.object(client,"_send",side_effect=send):self.assertEqual(client.predict([{"v":1},{"v":2},{"v":3}]),[1,2,3])
            self.assertEqual(sizes,[2,1])

    def test_invalid_cloud_outputs(self):
        client=QuickMLClient()
        for response in [{"result":[]},{"result":[{"prediction":"NaN"}]},{"result":[{"prediction":-1}]},{"result":[True]},{"wrong":123}]:
            with self.assertRaises(QuickMLError):client._extract(response,1)

    def test_no_silent_cloud_fallback(self):
        from gridpulse.forecasting import forecast
        with patch.dict(os.environ,{"FORECAST_BACKEND":"quickml"}),patch("gridpulse.forecasting.quickml_client") as factory:
            factory.return_value.predict.side_effect=QuickMLError("Provider unavailable")
            with self.assertRaisesRegex(QuickMLError,"Provider unavailable"):forecast(window())

    def test_errors_do_not_echo_credentials(self):
        client=QuickMLClient()
        with patch.object(client.opener,"open",side_effect=HTTPError(client.endpoint+"?secret-token",401,"secret-token",{},io.BytesIO(b'secret-key'))):
            with self.assertRaises(QuickMLError) as caught:client._send(Request(client.endpoint),"QuickML prediction")
        self.assertNotIn("secret",str(caught.exception));self.assertIn("401",str(caught.exception))

    def test_refresh_token_is_reused_before_expiry(self):
        with patch.dict(os.environ,{"QUICKML_REFRESH_TOKEN":"refresh","ZOHO_CLIENT_ID":"client","ZOHO_CLIENT_SECRET":"secret"}):
            client=QuickMLClient()
            with patch.object(client,"_send",return_value={"access_token":"new-token","expires_in":3600}) as send:
                self.assertEqual(client._access_token(),"new-token");self.assertEqual(client._access_token(),"new-token");self.assertEqual(send.call_count,1)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/"models/local_model.joblib").exists():raise unittest.SkipTest("Run python train.py first.")
        cls.env=patch.dict(os.environ,{"FORECAST_BACKEND":"local"});cls.env.start()
        from app import make_server
        cls.server=make_server(port=0);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.env.stop()

    def test_forecast_and_csv_upload(self):
        rows=json.loads(urlopen(self.url+"/api/demo").read())["rows"]
        for path,body in [("/api/forecast",{"rows":rows}),("/api/forecast-csv",{"csv":pd.DataFrame(rows).to_csv(index=False)})]:
            req=Request(self.url+path,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
            result=json.loads(urlopen(req).read());self.assertEqual(len(result["rows"]),24)
            self.assertEqual(result["backend"],"local");self.assertEqual(result["rows"][0]["timestamp"],rows[0]["timestamp"])
            for row in result["rows"]:
                self.assertEqual(row["critical_overload"],row["target_demand_kw"]>=200)

    def test_public_files_only_and_status_has_no_credentials(self):
        for path in ["/.env","/models/local_model.joblib","/../train_telemetry.csv","/gridpulse/config.py"]:
            with self.assertRaises(HTTPError) as caught:urlopen(self.url+path)
            self.assertEqual(caught.exception.code,404)
        data=urlopen(self.url+"/api/status").read().decode();self.assertNotIn("secret",data);self.assertIn("local_validation",data)
        for path in ["/","/app.js","/styles.css","/favicon.svg"]:self.assertEqual(urlopen(self.url+path).status,200)

    def test_bad_request_returns_clear_error(self):
        req=Request(self.url+"/api/forecast",data=b'{"rows":[]}',headers={"Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as caught:urlopen(req)
        self.assertEqual(caught.exception.code,400)

    def test_cli_preserves_arbitrary_row_order(self):
        frame=window().iloc[[9,1,23,2]].reset_index(drop=True)
        with tempfile.TemporaryDirectory() as d:
            inp,out=Path(d)/"input.csv",Path(d)/"output.csv";frame.to_csv(inp,index=False)
            run=subprocess.run([sys.executable,str(ROOT/"predict.py"),"--input",str(inp),"--output",str(out)],capture_output=True,text=True,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            result=pd.read_csv(out);self.assertEqual(result.columns.tolist(),["timestamp","target_demand_kw"])
            self.assertEqual(result.timestamp.tolist(),frame.timestamp.tolist());self.assertTrue(np.isfinite(result.target_demand_kw).all())


if __name__=="__main__":unittest.main(verbosity=2)
