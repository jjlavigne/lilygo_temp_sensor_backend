# Alerting: what is here and how to restore it

Two files, both **records** rather than provisioning inputs.

- `alert-rules.yaml` — the two live rules, exported 2026-09-04
- `contact-points.json` — the Slack contact point, **with the webhook URL
  replaced by a placeholder**. Grafana redacts that URL through every API, so it
  genuinely cannot be exported. Everything else — the name, and the custom
  message template that formats each alert — is preserved here, and rewriting
  that template from memory would be the tedious part of a rebuild.

## ⚠️ Never point Grafana's provisioning at these files

Alerting provisioning **replaces the notification configuration wholesale**. It
would delete the Slack contact point, and the webhook inside it is encrypted in
`grafana.db` and unreadable, so that loss is permanent.

Restore through the API instead, which also keeps the rules editable in the UI:

```bash
# 1. Contact point first -- rules route to it BY NAME, so it must exist first.
#    Paste your real webhook URL into contact-points.json, then:
curl -X POST http://localhost:3000/api/v1/provisioning/contact-points \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Disable-Provenance: true" \
  -d @contact-point.json

# 2. Then each rule from alert-rules.yaml
curl -X POST http://localhost:3000/api/v1/provisioning/alert-rules \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Disable-Provenance: true" \
  -d @rule.json

# 3. Confirm every rule query actually runs. A broken rule fails silently in the
#    scheduler and protects nothing -- this exact failure went unnoticed for a week.
python ../check_alert_rules.py
```

The contact point must be named **`Slack Integration`** exactly. Both rules use
simplified routing (`notification_settings.receiver`) and address it by that
string, so a different name means alerts fire and notify nobody.

## Getting the webhook URL

It is not recoverable from Grafana. Either:

- **From Slack**: <https://api.slack.com/apps> → your app → *Incoming Webhooks* →
  copy the URL, or
- **Regenerate**: same screen, *Add New Webhook to Workspace*, pick the channel.
  The old URL stops working, which is fine if nothing else uses it.

Restoring `grafana-storage-backup-*.tar.gz` brings the working webhook back
without any of this, and is the easier path when you have that archive.
