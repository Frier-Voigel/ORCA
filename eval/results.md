# Recovery evaluation (30 held-out scenarios)

| Policy | Mean downtime (service-seconds) | Mean services lost at end | Downtime reduction vs no action |
|---|---|---|---|
| no_action | 433.2 | 1.5 | 0.0% |
| naive_restart | 308.2 | 1 | 28.9% |
| ai_recommended | 157.5 | 0.5 | 63.6% |

## Intelligence Metrics (Predictor & RCA)

- **RCA Top-1 Accuracy**: 100%
- **RCA Top-3 Accuracy**: 100%
- **Predictor Root Cause Detection Rate**: 97%
- **Median Lead Time**: 50s warning before total failure
