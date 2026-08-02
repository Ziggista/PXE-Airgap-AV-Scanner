# PXE Client Hardening Notes

## Mandatory access control

For the Ubuntu PXE client, the current hardening track stages both `AppArmor` and a `SELinux` boot path, with SELinux now available for stricter enforcement experiments.

Reasons:

- Ubuntu ships with AppArmor as the native LSM path.
- SELinux on Ubuntu is community-supported rather than the default Ubuntu posture.
- Test builds can safely run SELinux in `permissive` mode to collect AVC logs before moving to `enforcing`.

## Current enforcement model

- The scanner desktop account is intentionally not a general `sudo` user.
- AV scans are expected to run as the unprivileged `scanner` user.
- Only source/destination mount helpers retain narrow `sudoers` delegation.
- Final copy is performed by a root broker after the unprivileged user raises a constrained request file.
- `av-network-enforcer.service` runs as root and re-checks the offline policy every 10 seconds.
- The enforcer drops network access once the splash is active or removable media is present.
- In test builds with post-splash debug explicitly enabled, the enforcer records a debug bypass instead of forcing the link down.

## SELinux rollout plan

- Test builds:
  - `pxe_client_test_mode: true`
  - `pxe_client_allow_post_splash_debug: true` only when active debug capture is needed
  - `pxe_client_selinux_mode: permissive`
- Production builds:
  - `pxe_client_test_mode: false`
  - `pxe_client_allow_post_splash_debug: false`
  - `pxe_client_selinux_mode: enforcing`

## Immediate next hardening steps

- Add SELinux policy modules for the scan launcher and media copy path after collecting AVC logs from the current test build.
- Consider removing `openssh-server` from production client builds entirely once debug validation is complete.
