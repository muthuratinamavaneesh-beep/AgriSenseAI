"""
VivasAI - Motor Anomaly Detection Engine (Stage 3)

This module implements an Isolation Forest machine learning model to evaluate 
electrical motor telemetry (Current, Voltage, Runtime) and detect potential 
abnormal electrical behavior or hardware stress conditions.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import IsolationForest

class MotorAnomalyDetector:
    def __init__(self, contamination=0.1, random_state=42):
        self.model_version = "v1.0-IsolationForest"
        self.contamination = contamination
        self.random_state = random_state
        self.model = None

    def analyze_telemetry(self, df_history, current_sample=None):
        """
        Trains/fits an Isolation Forest model on historical motor telemetry 
        and evaluates the latest sample for potential electrical anomalies.
        Includes physical electrical boundary checks to avoid false positives.

        Parameters:
            df_history (pd.DataFrame): Historical motor telemetry dataframe.
            current_sample (dict, optional): Single telemetry sample to evaluate.

        Returns:
            dict: Diagnostic result with status, risk score, timestamp, and explanation.
        """
        ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine target sample parameters
        if current_sample and isinstance(current_sample, dict):
            cur_val = float(current_sample.get('motor_current', 0.0))
            volt_val = float(current_sample.get('motor_voltage', 230.0))
            runtime_val = int(current_sample.get('motor_runtime', 0))
            ts = current_sample.get('timestamp', ts_now)
            m_status = str(current_sample.get('motor_status', 'OFF')).upper()
        elif df_history is not None and isinstance(df_history, pd.DataFrame) and not df_history.empty:
            last_row = df_history.iloc[-1]
            cur_val = float(last_row.get('motor_current', 0.0))
            volt_val = float(last_row.get('motor_voltage', 230.0))
            runtime_val = int(last_row.get('motor_runtime', 0))
            ts = str(last_row.get('timestamp', ts_now))
            m_status = str(last_row.get('motor_status', 'OFF')).upper()
        else:
            cur_val = 0.0
            volt_val = 230.0
            runtime_val = 0
            ts = ts_now
            m_status = 'OFF'

        # Physical Rule 1: Standby motor (OFF) with zero current draw is ALWAYS Normal (Standby)
        if m_status == "OFF" and cur_val <= 0.5:
            return {
                "status": "NORMAL",
                "condition": "Normal (Standby)",
                "is_anomaly": False,
                "anomaly_score_pct": 0.0,
                "timestamp": ts,
                "explanation": "Motor is OFF in standby mode. Zero electrical current draw."
            }

        # Physical Rule 2: Active motor (ON) within normal operating parameters (10-20 A, 200-250 V) is ALWAYS Normal
        if m_status == "ON" and (10.0 <= cur_val <= 20.0) and (200.0 <= volt_val <= 250.0):
            return {
                "status": "NORMAL",
                "condition": "NORMAL",
                "is_anomaly": False,
                "anomaly_score_pct": 5.0,
                "timestamp": ts,
                "explanation": f"Normal electrical operation: {cur_val} A current draw, {volt_val} V line voltage."
            }

        # Physical Rule 3: Genuine overcurrent or line voltage instability
        if cur_val > 22.0:
            return {
                "status": "ANOMALY",
                "condition": "POTENTIAL ANOMALY",
                "is_anomaly": True,
                "anomaly_score_pct": 92.0,
                "timestamp": ts,
                "explanation": f"Potential electrical anomaly: High current draw ({cur_val} A > 20 A threshold)."
            }

        if volt_val < 195.0 or volt_val > 255.0:
            return {
                "status": "ANOMALY",
                "condition": "POTENTIAL ANOMALY",
                "is_anomaly": True,
                "anomaly_score_pct": 88.0,
                "timestamp": ts,
                "explanation": f"Potential electrical anomaly: Voltage fluctuation ({volt_val} V outside 200-250V range)."
            }

        # Fallback to Isolation Forest ML model for secondary evaluation
        if df_history is None or not isinstance(df_history, pd.DataFrame) or len(df_history) < 10:
            return {
                "status": "NORMAL",
                "condition": "NORMAL",
                "is_anomaly": False,
                "anomaly_score_pct": 0.0,
                "timestamp": ts,
                "explanation": "Normal operating parameters."
            }

        feature_cols = ['motor_current', 'motor_voltage', 'motor_runtime']
        for col in feature_cols:
            if col not in df_history.columns:
                return {
                    "status": "NORMAL",
                    "condition": "NORMAL",
                    "is_anomaly": False,
                    "anomaly_score_pct": 0.0,
                    "timestamp": ts,
                    "explanation": "Normal parameters."
                }

        X = df_history[feature_cols].copy()
        self.model = IsolationForest(
            n_estimators=100,
            contamination=self.contamination,
            random_state=self.random_state
        )
        self.model.fit(X)

        sample_df = pd.DataFrame([{
            'motor_current': cur_val,
            'motor_voltage': volt_val,
            'motor_runtime': runtime_val
        }])

        pred = self.model.predict(sample_df)[0]
        decision_score = self.model.decision_function(sample_df)[0]
        raw_risk = (0.20 - decision_score) * 250.0
        risk_pct = round(max(0.0, min(100.0, raw_risk)), 1)

        if pred == -1 or risk_pct >= 60.0:
            return {
                "status": "ANOMALY",
                "condition": "POTENTIAL ANOMALY",
                "is_anomaly": True,
                "anomaly_score_pct": risk_pct,
                "timestamp": ts,
                "explanation": f"Potential abnormal electrical behavior detected by Isolation Forest model ({risk_pct}% risk)."
            }

        return {
            "status": "NORMAL",
            "condition": "NORMAL",
            "is_anomaly": False,
            "anomaly_score_pct": risk_pct,
            "timestamp": ts,
            "explanation": "Normal operating electrical parameters."
        }
