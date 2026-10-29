# The administrator's password on the hosted site

Copy `admin.example.toml` from the top of the repository here as `admin.toml` and set the password in it (roadmap R149). `compose.yaml` mounts this folder into the app read-only, and the app reads the file again whenever it changes, so there is no restart. `admin.toml` is never committed. Every step is in [docs/guides/Admin-Password-Guide.pdf](../../docs/guides/Admin-Password-Guide.pdf).

To let only some laptops sign in as the administrator (roadmap R163), copy `admin-laptops.example.toml` from the top of the repository here as `admin-laptops.toml` and list each laptop's ID, shown on the Settings page. The app finds it beside `admin.toml` and reads it again whenever it changes. With no such file, any laptop can sign in. `admin-laptops.toml` is never committed.
