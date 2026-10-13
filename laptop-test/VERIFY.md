# Verification status

Automated checks here verify software behavior, not human fall-detection accuracy.

- Seven temporal rule tests cover a fall-like transition, single latched event, sitting, tracking loss, long gaps, already-horizontal startup posture, recovery from a short transition, and acknowledgement reset.
- The package is designed for Python 3.12 x64 on Windows with a private CPU environment.
- Actual ASUS laptop performance, live-camera tracking, and held-out fall accuracy must be measured by running the package on that laptop.

Packaging checks passed on Windows with Python 3.12.10:

- Installed dependencies; `pip check` reports no broken requirements.
- CPU-only model initialized and completed inference on a blank frame.
- A two-second synthetic blank video completed the headless recorded-video path and generated metrics, summary, and events files with no pose or fall alerts.
- Seven temporal logic tests passed.

The blank video validates execution and logging only. It does not validate pose accuracy, fall accuracy, live-camera behavior, or the user's laptop speed.

Official model bundle SHA256: `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`. The installer checks this value. Model source is documented in README.md.
