-- Least-privilege grants for the Databricks App service principal (role auto-created by the app's postgres resource)
GRANT USAGE ON SCHEMA smb_cashflow TO "<app-sp-client-id>";
GRANT SELECT ON ALL TABLES IN SCHEMA smb_cashflow TO "<app-sp-client-id>";
GRANT USAGE ON SCHEMA app TO "<app-sp-client-id>";
GRANT SELECT, INSERT ON app.agent_actions, app.copilot_audit TO "<app-sp-client-id>";
GRANT SELECT ON app.note_vectors TO "<app-sp-client-id>";
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO "<app-sp-client-id>";
