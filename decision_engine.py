import datetime
from database.database import get_all_farm_config

class SmartDecisionEngine:
    def __init__(self):
        self.version = 'v1.0-RuleBased'

    def evaluate(self, soil_moisture, crop_type, crop_stage, weather, water_level, motor_status, motor_anomaly_status, schedule, recent_irrigation_hours=None, automation_mode='MANUAL') -> dict:
        config = get_all_farm_config()
        min_water_level = float(config.get('min_water_level', 20.0))
        soil_moisture_target = float(config.get('soil_moisture_target', 60.0))
        rainfall_threshold = float(config.get('rainfall_threshold', 50.0))
        min_duration = int(config.get('min_irrigation_duration', 10))
        max_duration = int(config.get('max_irrigation_duration', 60))

        factors = []
        safety_checks = self.check_safety(water_level, motor_anomaly_status, weather, schedule, min_water_level, rainfall_threshold)
        need_score, need_level, need_factors = self.calculate_irrigation_need_score(soil_moisture, crop_type, crop_stage, weather, soil_moisture_target)
        
        factors.extend(need_factors)

        # Check blockers
        if water_level < min_water_level:
            factors.append(f'⚠ Low water level: {water_level}% (Minimum: {min_water_level}%)')
            return self._build_result('BLOCKED', 'Insufficient water level', 'CRITICAL', need_level, 0, 1.0, False, safety_checks, factors)
        else:
            factors.append(f'✓ Water level: {water_level}%')

        if motor_anomaly_status == 'ANOMALY':
            factors.append(f'⚠ Motor anomaly detected')
            return self._build_result('BLOCKED', 'Motor anomaly detected', 'CRITICAL', need_level, 0, 0.9, False, safety_checks, factors)
        else:
            factors.append(f'✓ Motor condition: {motor_anomaly_status}')

        # Check rain
        rain_prob = float(weather.get('rain_probability', 0))
        expected_rain = float(weather.get('expected_rainfall_mm', 0))
        if rain_prob > rainfall_threshold and expected_rain > 5:
            factors.append(f'🌧 High rain probability: {rain_prob}% with {expected_rain}mm expected')
            return self._build_result('DELAY', 'Rain expected soon', 'MEDIUM', need_level, 0, 0.8, False, safety_checks, factors)
        else:
            factors.append(f'✓ Rain probability: {rain_prob}%')

        # Determine decision based on need
        if need_score < 25:
            decision = 'SKIP'
            reason = 'Soil moisture is sufficient'
            priority = 'LOW'
            duration = 0
        else:
            decision = 'IRRIGATE'
            if need_score > 75:
                reason = 'Critical dryness detected'
                priority = 'CRITICAL'
            elif need_score > 50:
                reason = 'High irrigation need'
                priority = 'HIGH'
            else:
                reason = 'Moderate irrigation need'
                priority = 'MEDIUM'
            duration = self.calculate_duration(need_score, crop_type, weather, min_duration, max_duration)

        automation_allowed = all(safety_checks.values()) and automation_mode == 'AUTOMATIC'

        if motor_status == 'ON':
            factors.append('✓ Motor active & irrigating field')
            reason = "Irrigation cycle in progress (Motor ON)"
            decision = 'IRRIGATE'
        elif decision == 'IRRIGATE' and motor_status == 'OFF' and not automation_allowed:
            factors.append('⚠ Motor OFF and automation not allowed')
            reason += " (Recommend manual start)"

        return self._build_result(decision, reason, priority, need_level, duration, 0.85, automation_allowed, safety_checks, factors)

    def _build_result(self, decision, reason, priority, irrigation_need, recommended_duration, confidence, automation_allowed, safety_checks, factors):
        return {
            'decision': decision,
            'reason': reason,
            'priority': priority,
            'irrigation_need': irrigation_need,
            'recommended_duration': recommended_duration,
            'confidence': confidence,
            'automation_allowed': automation_allowed,
            'safety_checks': safety_checks,
            'factors': factors,
            'timestamp': datetime.datetime.now().isoformat(),
            'engine_version': self.version
        }

    def check_safety(self, water_level, motor_anomaly_status, weather, schedule, min_water_level, rainfall_threshold) -> dict:
        rain_prob = float(weather.get('rain_probability', 0))
        expected_rain = float(weather.get('expected_rainfall_mm', 0))
        return {
            'water_level_safe': water_level > min_water_level,
            'motor_healthy': motor_anomaly_status != 'ANOMALY',
            'no_schedule_conflict': True,  # Simplified for now
            'weather_acceptable': rain_prob < rainfall_threshold or expected_rain < 5,
            'sufficient_water': water_level > 30.0
        }

    def calculate_irrigation_need_score(self, soil_moisture, crop_type, crop_stage, weather, soil_moisture_target) -> tuple[float, str, list]:
        factors = []
        score = max(0.0, (soil_moisture_target - soil_moisture) / soil_moisture_target * 100.0)

        if soil_moisture < 25:
            score += 25
            factors.append(f'⚠ Critical dryness: {soil_moisture}%')
        elif soil_moisture < 40:
            score += 15
            factors.append(f'⚠ Low soil moisture: {soil_moisture}%')
        else:
            factors.append(f'✓ Soil moisture: {soil_moisture}%')

        stage_multipliers = {
            'Germination': 1.2,
            'Vegetative': 1.0,
            'Flowering': 1.3,
            'Fruiting': 1.1,
            'Maturity': 0.7
        }
        mult = stage_multipliers.get(crop_stage, 1.0)
        score *= mult
        factors.append(f'Crop stage ({crop_stage}) multiplier: {mult}x')

        temp = float(weather.get('temperature', 25.0))
        humidity = float(weather.get('humidity', 50.0))

        if temp > 40:
            score += 15
            factors.append(f'⚠ Extreme temperature: {temp}°C')
        elif temp > 35:
            score += 10
            factors.append(f'⚠ High temperature: {temp}°C')

        if humidity < 40:
            score += 10
            factors.append(f'⚠ Dry air: {humidity}% humidity')

        score = min(100.0, score)

        if score < 25:
            level = 'LOW'
        elif score < 50:
            level = 'MEDIUM'
        elif score < 75:
            level = 'HIGH'
        else:
            level = 'CRITICAL'

        return score, level, factors

    def calculate_duration(self, need_score, crop_type, weather, min_duration, max_duration) -> int:
        base_dur = min_duration + (max_duration - min_duration) * (need_score / 100.0)

        expected_rain = float(weather.get('expected_rainfall_mm', 0))
        base_dur -= expected_rain * 2

        crop_adjustments = {
            'Paddy': 1.4,
            'Cotton': 0.8,
            'Wheat': 1.0,
            'Tomato': 0.9,
            'Maize': 1.1
        }
        adj = crop_adjustments.get(crop_type, 1.0)
        base_dur *= adj

        final_dur = int(max(min_duration, min(max_duration, base_dur)))
        return final_dur
