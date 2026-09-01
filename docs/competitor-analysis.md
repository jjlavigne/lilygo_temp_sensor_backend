# SmartSense — what Plymouth is actually running

Analysis of Digi SmartSense as deployed at Plymouth Poultry, from the live
account (screenshots, 1 Sept 2026) and quote #145514. Everything here is
observed from their own screens and report exports, not from marketing material.

---

## Scale of the deployment

**59 assets** across at least six sites:

| Site |
|---|
| Plymouth Aloha |
| Plymouth Auburn |
| Plymouth Seattle |
| Plymouth Phoenix |
| Kent Cold Storage |
| Frontier Transport |

Assets are named by function: *South Loading, West Cooler, Blast freezer, Frontier
Avocado Room, Frontier Freezer 1/2, 107AF4 Cooler Dock, NW Cooler, G21 Hard Chill*.

**Cost implication.** The subscription is $100/month **per site**. Six sites is
$7,200/year in subscriptions alone, before hardware and before NIST
recertification. Quote #145514 covers only the *new* Auburn location at $9,202
for its first year — the fleet-wide figure is several times larger.

---

## The headline finding: 306 of 354 alarms are not configured

Their own **Alarm Configuration Report**:

- Total asset count: **59**
- Alarms **Complete: 48**
- Alarms **Not Configured: 306**

Each asset supports six alarm types — High Temperature, Low Temperature, High
Humidity, Low Humidity, Low Battery, and **Missed Report** (their name for
offline detection). Typically only High Temperature is configured:

| Asset | High Temp | Low Temp | Low Battery | Missed Report |
|---|---|---|---|---|
| Frontier Avocado Room | not configured | not configured | not configured | not configured |
| Frontier Freezer 1 | "Too warm" | not configured | not configured | not configured |
| Frontier Freezer 2 | configured | not configured | not configured | not configured |

**What this means in practice:** across most of the fleet, a dead sensor raises
nothing, a flat battery gives no warning, and freeze damage goes unnoticed. The
system is watching for one failure mode out of six.

**Why our design cannot have this problem.** Our three alert rules read limits
from the `devices` table and evaluate every registered device. There is no
per-asset, per-alarm-type configuration to complete or forget. Their architecture
requires 354 decisions; ours requires none.

---

## Roughly 14 assets have no thresholds at all

In **Asset Health – Details**, a block of assets shows asset score "No score" and
prescriptive action **"Check Threshold Settings"** — including *N.W. Freezer,
S.E. Freezer, CAN #1, CAN #2, West Loading Dock, 405AS1 New Freezer, Frontier
Avocado Room, B181 B Freezer, N.E. Freezer, S&J office West side, North Dry*.

These are monitored in name only.

---

## The dashboard shows 15 incidents that have already resolved

The front page lists **15 High Severity Incidents**. Their "Currently" readings
show most are already back inside their limits:

| Incident | Threshold breached | Currently | Age |
|---|---|---|---|
| South Loading | above 44 °F for 1h 15m | 40.44 °F | 11 hours |
| South Loading | above 44 °F for 4h 00m | 40.44 °F | 20 hours |
| South Loading | above 44 °F for 3h 00m | 39.76 °F | 20 hours |
| Blast freezer | above 10 °F for 2h 45m | 5.34 °F | 2 days |
| West Cooler | above 40 °F for 15m | 39.65 °F | 2 days |

Incident 100446820's own history reads:

```
10 hours ago   Status Change   Alarm status changed to 'Resolved'
10 hours ago   Information     All Alarm Events have resolved.
11 hours ago   Notification    Email sent to Travis.erickson@plymouthinc.com
11 hours ago   Notification    Email sent to stephen.speiser@nickyusa.com
```

The system knows it resolved. The incident is still status **New** and still on
the dashboard, because acknowledgement is manual and nobody clicked it.

**The headline number does not reflect reality.** That is alert fatigue as a
design outcome — the primary screen is a backlog, not a status board.

Our alerts resolve themselves when the temperature returns to range and send a
recovery notification. The dashboard shows current state.

---

## Sensors report every 15 minutes

From the 107AF4 Cooler Dock readings: 10:24:48, 10:09:48, 09:54:48, 09:39:48,
09:24:48, 09:09:48.

A door left open for ten minutes can pass entirely between samples. Our simulated
fleet reports every 5 minutes and the physical board every 5 seconds.

---

## Four assets are failing, and have been for some time

From **Asset Health – Details**, percent of time inside limits:

| Asset | In range | Incidents | Grade |
|---|---|---|---|
| Plymouth Phoenix 3 | **54.28%** | 21 | Poor |
| South Loading | **62.66%** | 15 | Poor |
| Plymouth Phoenix 1 | 66.71% | 12 | Poor |
| Plymouth Phoenix 2 | 72.96% | 12 | Poor |
| Blast freezer | 89.26% | 4 | Average |
| West Cooler | 96.56% | 8 | Average |

Phoenix 3 is outside its limits nearly half the time. Either the equipment is
failing or the thresholds are wrong; either way it has been that way long enough
to accumulate 21 incidents.

---

## Feature inventory — what they have

Navigation: **Dashboard · Assets · Gateways · Reports · Incidents · Admin**

Notably **no Jolt, checklists or task management** in this account. Plymouth uses
SmartSense for temperature monitoring only, so a monitoring replacement is a
complete replacement.

**Incident handling**
- Acknowledge button
- Assign to a named person
- Status workflow (New → …)
- Per-incident history log: status changes, notifications sent, with recipients
- **Corrective Actions** capture
- Email notification, logged per incident with recipient address

**Reporting**
- **Incident Details** export: start time, **duration**, severity classified as
  Short (<1h) / Medium (1–3h) / Long (>3h), status, asset, threshold type and
  name, **max / min / average reading** per incident
- **Alarm Configuration Report**: which alarms are set up, which are not
- **Asset Health**: asset score, grade, **percent in range**, incident count,
  and a *prescriptive action* ("Lower Setpoint / Raise Threshold", "Check
  Threshold Settings", "No Action Needed")
- History back to at least 2023

**Asset view**
- Time range presets (Today, Yesterday, Last 7 Days, Last Month) plus custom range
- Chart with drag-to-zoom
- Last Readings table
- **Data export** (download button)
- Two probes per asset — a standard one and a NIST-certified one, charted together

**Hardware**
- Wireless sensors on a proprietary radio, requiring **cellular/LoRaWAN gateways**
  ($599 each, 4 on the Auburn quote)
- Humidity as well as temperature on some assets
- NIST certification per probe, **expiring every 24 months** ($125 each)

---

## Their structural weaknesses

1. **Configuration burden** — 354 alarm decisions, 306 left undone
2. **Manual acknowledgement** — resolved incidents stay on the dashboard indefinitely
3. **15-minute sampling** — short excursions can be invisible
4. **Gateways required** — a consequence of putting the sensor *inside* the
   freezer; ours mounts outside with only the probe through the gasket
5. **Data lives in Digi's cloud** — no local copy, no control over pricing or terms
6. **NIST recertification** presented as a one-time cost but recurring every 2 years
7. **Per-site subscription** — cost scales with the business

---

## Honest assessment of where we stand

**They are ahead on:** incident lifecycle (acknowledge, assign, corrective
actions), reporting depth (duration, severity banding, percent in range, min/max/avg),
email and SMS notification, data export, humidity, mobile app.

**We are ahead on:** alerts that cannot be left unconfigured, auto-resolving
incidents, sampling rate, cost, data ownership, no gateway requirement.

Two things previously assumed to be our differentiators — **excursion duration**
and **percent time in range** — are things SmartSense already has. They are parity
requirements, not advantages. See `docs/roadmap.md`.
