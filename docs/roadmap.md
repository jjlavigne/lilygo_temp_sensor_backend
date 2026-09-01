# Roadmap

> **Done (1 Sept 2026).** Needs Attention, Margin to Nearest Limit, Time In Range,
> and a readable fleet temperature chart. Revert point: `git tag pre-ui-overhaul`.
> Items 1 (full incident tracking) and 4–8 below remain open.


Candidate changes, ranked. Effort estimates assume the existing stack; nothing
here requires new infrastructure.

Categories:
- **Parity** — SmartSense has it and we don't. Closing a gap someone will notice.
- **Advantage** — something they cannot easily do, given their architecture.
- **Later** — real, but not before a pilot has run.

See `docs/competitor-analysis.md` for the evidence behind each.

---

## 1 · Incident tracking — PARITY — ~half a day

**The gap.** We alert when a device goes out of range and again when it recovers,
but nothing records the excursion as an *event*. Nobody can answer "how bad was
that?" the next morning.

SmartSense records start time, **duration**, severity banded as Short (<1h) /
Medium (1–3h) / Long (>3h), and **max / min / average** reading per incident.

**Why it matters.** Food safety is time *and* temperature. Ten minutes at 40 °F is
a door being opened; four hours is a written-off load. Without duration we cannot
tell those apart, and neither can an auditor.

**Shape.** An `incidents` table written by a small watcher: device, started_at,
ended_at, peak reading, average, duration. Then a panel listing recent incidents
and a per-incident view.

---

## 2 · Percent time in range — PARITY — ~2 hours

**The gap.** Their Asset Health report scores every asset by the share of time it
spent inside its limits, which is how they surfaced that Plymouth Phoenix 3 sits
at 54%.

**Why it matters.** It is the single number a customer or auditor asks for, and
it turns "we send alerts" into "here is the state of your cold chain."

**Shape.** One query over `telemetry` joined to `devices`, grouped by month. A stat
panel per device and a fleet table. Straightforward once incidents exist, and
useful even before.

---

## 3 · Email alerts alongside Slack — PARITY — ~1 hour

**The gap.** They notify by email, SMS and phone; we do Slack only. Their incident
log shows emails going to named recipients at plymouthinc.com and nickyusa.com.

**Why it matters.** Not everyone is in Slack, and "does it email me?" is an easy
objection to remove.

**Shape.** Grafana supports email contact points natively — SMTP settings on the
grafana service, then a second contact point. SMS would need Twilio and is not
worth it yet.

---

## 4 · Acknowledge and assign — PARITY, with a caveat — ~half a day

**The gap.** No way to mark an alert as being dealt with, or to say who owns it.

**The caveat.** Their manual acknowledgement is exactly what left 15 resolved
incidents sitting on their dashboard. **Copy the assignment, keep our auto-resolve.**
An acknowledged incident should still close itself when the temperature recovers.

---

## 5 · Corrective action logging — PARITY — ~half a day

**The gap.** When an excursion happens, nothing records what was done about it.

**Why it matters.** This is the HACCP-relevant piece: an auditor asks not only
"did it go out of range" but "what did you do." Pairs naturally with incidents.

**Shape.** A note attached to an incident — who responded, what they found, what
action was taken, timestamp.

---

## 6 · Audit log for threshold changes — ADVANTAGE — ~2–3 hours

**The gap.** Nothing records who changed a temperature limit, or what it was
before.

**Why it matters.** If a ceiling quietly moves from 34 °F to 45 °F and product
spoils, there is currently no way to find out who did it or when. In a compliance
system that is a real hole — and one their Alarm Configuration Report suggests
they also have, since it shows *what* is configured but not *who changed it*.

**Shape.** A `device_changes` table written by the admin UI: user, field, old
value, new value, timestamp. Plus a recent-activity page.

---

## 7 · Data export — PARITY — ~1 hour

**The gap.** Their asset view has a download button; ours has none.

**Why it matters.** Auditors and insurers ask for raw data. Grafana's table panels
support CSV export out of the box — it may only need enabling and testing.

---

## 8 · User management in the UI — LATER — ~1–2 hours

Adding a person or restricting them to one company currently needs SQL. The
scoping works; there is simply no screen for it. Necessary the moment a second
person needs access.

---

## 9 · Asset layer — LATER — ~half a day

Separating *the sensor* from *the thing being monitored*, so a freezer keeps
continuous history across hardware replacements while every reading still names
the sensor that took it.

**Not before a pilot.** It shows nothing until a sensor has been replaced, it
touches the core data model, and after one real replacement we will know how it
actually behaves rather than guessing.

---

## 10 · Humidity — LATER

Some of their assets monitor humidity as well as temperature. Our payload and
schema are temperature-only. Worth knowing if any Plymouth asset depends on it;
adding a column and a sensor is not difficult, but nothing calls for it yet.

---

## Explicitly not doing

**Digital checklists / task management.** SmartSense sells this (Jolt), but
Plymouth's account does not have it — their navigation is Dashboard, Assets,
Gateways, Reports, Incidents, Admin. Building an operations platform is a
different product.

**Mobile app.** The dashboard is responsive and reachable on a phone over the
network. A native app solves nothing we have.

**Predictive analytics.** Their marketing claims it; their screens show a
"prescriptive action" column with three canned strings. Not worth chasing.

---

## Suggested order

1 and 2 together — they share a query and produce the compliance report that is
currently the clearest thing SmartSense has and we do not. Then 3, since it is an
hour and removes an objection. Then 6, because it protects against a failure that
is silent and expensive. The rest after a pilot.
