# Server operations

Private deployment records, backup/recovery procedures, inventory and Linux assessment: [NOVA server infrastructure](https://github.com/IoloHJ/nova-server-infrastructure). Filled environments, databases, provider credentials and household state must stay outside source control.

The three existing application/tunnel/refresh containers use `unless-stopped`; the policy was applied live without restarting them. Compose now defines HTTP health and waits for application health before dependent services start on a future recreation. The live host watchdog independently checks application HTTP and SQLite readability. No application source or database schema was changed. Existing working edits remain untouched.
