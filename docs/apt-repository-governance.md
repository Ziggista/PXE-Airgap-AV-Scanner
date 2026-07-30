# APT Repository Governance

## Purpose

Item 1 should be the controlled package intake point for Linux-hosted infrastructure in this project.

Its job is to:

- mirror approved upstream Debian/Ubuntu package repositories;
- snapshot and publish vetted package sets for downstream use;
- sign published repositories so build-side consumers trust only our copy;
- avoid direct `apt` access from the PXE build environment to the public internet.

Its job is not to:

- replace workstation-side acquisition for non-APT artifacts such as Ubuntu live ISOs, AV engines, vendor binaries, or offline signature bundles;
- act as a generic file mirror for arbitrary internet downloads;
- allow the build VM to pull directly from unapproved third-party repositories.

## Recommended Stack

Use this stack for Item 1:

1. `aptly` as the repository management system.
2. `nginx` as the static HTTP publication layer.
3. `gpg` for repository signing.
4. `systemd` timers or CI jobs for controlled mirror update and publish runs.

### Why `aptly`

`aptly` is the right fit because it supports the full lifecycle we need:

- mirroring upstream Debian-style repositories;
- immutable snapshots;
- local repositories for internally-added `.deb` packages;
- signed publication of repositories that downstream `apt` clients can consume;
- an API if we later want policy-driven automation.

This matters more than raw mirroring alone because the build side should consume curated snapshots, not live upstream state.

### Why not use a plain mirror only

Tools that only mirror repositories are weaker for this design because they do not give us the same controlled promotion model. The design goal is:

1. mirror;
2. snapshot;
3. verify;
4. publish a stable signed view;
5. let the build server consume only that published view.

That makes rollback and incident response much cleaner.

## Architectural Role

The Ubuntu proxy VM should become an APT publication VM rather than a generic proxy.

Recommended role split:

- `av-repo-vm`
  - internet egress allowed;
  - runs `aptly`;
  - pulls from approved upstream APT repositories;
  - stores mirrors, snapshots, and published trees;
  - serves signed published repositories over HTTP.

- `av-build-vm`
  - no direct public APT access;
  - consumes only published repositories from `av-repo-vm`;
  - hosts PXE/TFTP/iPXE and downstream boot assets;
  - stages non-APT artifacts separately.

- `workstation-acquisition-host`
  - fetches non-APT vendor content;
  - verifies hashes/signatures where possible;
  - publishes those artifacts into a separate controlled store for the build VM.

## Governance Rules

### 1. Approved source classes

Allow only these source classes:

- Ubuntu official archives required for the Ubuntu VMs in this solution;
- Debian official archives only if a specific component requires Debian packages;
- vendor repositories with documented business need and package signing;
- internal local repositories for self-built or manually imported `.deb` packages.

Disallow by default:

- personal PPAs;
- community repos without a support owner;
- repos that require disabling signature verification;
- repos added ad hoc on a build VM;
- “curl | bash” installers as a substitute for repository governance.

### 2. Publish only from snapshots

Never publish directly from a live mirror for production consumption.

Required flow:

1. Update mirror.
2. Create snapshot.
3. Validate package intent and changes.
4. Publish the snapshot under a controlled prefix.
5. Point clients at the published snapshot.

This creates a stable package baseline for rebuilds and forensics.

### 3. Separate channels

Maintain at least three channels:

- `baseline`: current approved production packages;
- `candidate`: newly mirrored packages awaiting validation;
- `emergency`: temporary publication for urgent security response.

The build VM should default to `baseline`.

### 4. Repository signing is mandatory

All published repositories must be signed with an internal GPG signing key.

Rules:

- clients trust only the exported public key from this project;
- upstream trust is verified during mirror intake;
- signing keys must be backed up and rotated under change control;
- unsigned publication is not allowed outside isolated lab testing.

### 5. Minimize scope

Mirror only what is needed.

Prefer limiting by:

- distribution or suite;
- component;
- architecture;
- package filters where operationally safe.

For this project, `amd64` should be the default architecture unless a real ARM target appears.

### 6. Keep APT and non-APT content separate

Do not force non-APT artifacts into the APT repository unless they are packaged intentionally as `.deb` content for Ubuntu consumers.

Keep separate stores for:

- APT packages and metadata;
- PXE boot files;
- Ubuntu live images or custom boot images;
- AV engine bundles;
- offline signature files;
- removable-media workflow outputs.

This avoids turning the APT repo into an unstructured file dump.

## What We Should Mirror

Start narrow.

### Required initial upstreams

- Ubuntu LTS base repositories for the Ubuntu version used by `av-repo-vm` and `av-build-vm`;
- Ubuntu security and updates pockets for that same release;
- any official Ubuntu packages needed for PXE services such as `dnsmasq`, `nginx`, `tftpd` or equivalent, `ipxe`, and supporting tooling.

### Optional upstreams

- a vendor repository for a required operational tool, but only after approval and key validation;
- a Debian upstream mirror if a required package is unavailable or unsuitable from Ubuntu.

### Not part of the APT mirror

These should remain in the workstation acquisition lane or a separate artifact store:

- Ubuntu live ISO customizations and boot artifacts that are not being published as `.deb` packages;
- portable AV scanners distributed as `.bin`, `.tar.gz`, `.deb`, `.run`, `.zip`, or vendor-specific formats;
- offline DAT, pattern, or signature archives;
- firmware tools, BIOS utilities, and other bare vendor binaries.

## Suggested Publication Layout

Use a simple published tree structure:

- `/ubuntu/baseline`
- `/ubuntu/candidate`
- `/ubuntu/emergency`
- `/internal/tools`

Use a matching internal naming convention for mirrors and snapshots:

- mirrors: `ubuntu-<release>-<pocket>`
- snapshots: `ubuntu-<release>-<pocket>-YYYYMMDD`
- publications: `<channel>/<release>`

Example:

- mirror: `ubuntu-24.04-updates`
- snapshot: `ubuntu-24.04-updates-20260730`
- publication: `baseline/24.04`

## Promotion Workflow

1. Scheduled intake job updates approved mirrors.
2. A snapshot is created with the current date stamp.
3. A diff is reviewed against the previously published snapshot.
4. Candidate publication is updated.
5. Validation is run on a non-production Ubuntu build VM.
6. If approved, the same snapshot is promoted to baseline.
7. Emergency fixes are published separately and later reconciled back into baseline.

## Security Controls

- Outbound internet from `av-build-vm` should be blocked for APT.
- Only `av-repo-vm` is allowed to contact upstream package repositories.
- Store mirror and publication logs centrally.
- Keep an audit trail of:
  - approved upstream URL;
  - signing key fingerprint;
  - snapshot date;
  - published channel;
  - approver;
  - rollback target.

## Operational Controls

- Mirror updates should run on a schedule, not manually from shell history.
- Snapshot retention should keep enough history for rollback and investigation.
- Package deletion from published history should be rare and documented.
- Large repository expansion requires capacity review for disk, backup, and restore time.

Recommended minimum retention:

- 30 days of daily snapshots;
- 12 monthly anchor snapshots;
- the last known-good snapshot for each published channel.

## Tooling Standard

Standardize on:

- `aptly` for mirror, snapshot, local repo, and publish operations;
- `nginx` for serving the published tree;
- `systemd` for service and scheduled execution;
- a small policy file in this repository that defines approved upstreams, suites, components, and architectures.

Avoid mixed tooling unless there is a hard requirement. Running multiple repo managers usually creates avoidable state drift.

## Decision

Item 1 should be implemented as a signed `aptly`-managed APT repository service on Ubuntu, fronted by `nginx`, with snapshot-based promotion and a strict upstream allowlist.

The build VM should never install directly from the internet. It should consume only approved signed publications from Item 1.

Non-APT content should continue through a separate workstation acquisition and artifact-publishing workflow.
