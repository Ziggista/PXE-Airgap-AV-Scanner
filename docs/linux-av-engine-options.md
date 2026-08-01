# Linux AV Engine Options

This note captures practical Linux AV and endpoint security options for the PXE air-gap scanner as of July 30, 2026.

## Short version

Best fit for the first build:

1. `ClamAV`
2. `ESET Server Security for Linux`
3. `Microsoft Defender for Endpoint on Linux`
4. `Sophos Protection for Linux`

Not a fit for the offline one-shot scanner design:

- `Huntress Linux agent`

## Important constraint

Do not assume that multiple commercial Linux AV products can be installed side by side on the same live image.

At least some vendors explicitly warn against running more than one antivirus product on the same system. In practice, the safest model is usually:

- one open-source scanner that can coexist easily, such as `ClamAV`
- one commercial engine per image, or
- separate disposable scan environments if you want true multi-engine comparison

## Candidate engines

### ClamAV

Fit:

- good fit for offline one-shot scanning
- easy to script
- easy to package into a PXE boot image

What it does:

- command-line scanning with `clamscan`
- daemon mode with `clamd`
- signature updates with `freshclam`

Licensing:

- open source
- GPLv2

Operational notes:

- simplest baseline engine to include first
- detection quality is useful but should not be treated as equivalent to a full commercial EDR/AV stack

Official sources:

- [ClamAV Documentation](https://docs.clamav.net/)
- [ClamAV Usage Guide](https://docs.clamav.net/manual/Usage.html)

### Sophos Protection for Linux

Fit:

- technically usable for on-demand scans on Linux
- more appropriate for a licensed commercial build than a quick community-style offline scanner

What it does:

- local on-demand scanning via `avscanner`
- can scan files, directories, and archives
- return codes are documented for scripted handling

Licensing:

- commercial
- managed under Sophos licensing and Sophos Central / server protection product lines
- no public self-serve free Linux scanner entitlement was identified in the official licensing pages reviewed

Operational notes:

- better fit if you already own Sophos server protection licensing
- likely heavier operationally than `ClamAV`

Official sources:

- [Sophos Protection for Linux: Server Protection agent](https://docs.sophos.com/esg/spl/en-us/help/ServerProtectionAgent/index.html)
- [Sophos Protection for Linux distribution support](https://docs.sophos.com/esg/spl/en-us/support/ServerProtectionAgentDistributionKernelSupport/index.html)
- [Sophos licensing guidelines](https://www.sophos.com/en-us/legal/license-entitlement-and-usage-policy)
- [Sophos server security pricing](https://www.sophos.com/en-us/products/server-security/get-pricing)

### Huntress Linux agent

Fit:

- not a fit for the offline PXE one-shot scanner design

Why not:

- requires the Huntress platform
- requires account and organization keys
- requires reliable HTTPS access to Huntress cloud services
- product is managed EDR, not a simple offline drop-in scanner

Licensing:

- commercial subscription
- priced per endpoint

Operational notes:

- good managed Linux EDR product in connected environments
- poor fit for RAM-only offline media scanning

Official sources:

- [Huntress Linux installation and system requirements](https://support.huntress.io/hc/en-us/articles/42457934554003-Linux-Installation-and-System-Requirements)
- [Huntress Windows install article showing account and organization key requirements](https://support.huntress.io/hc/en-us/articles/4404005189011-Install-the-Huntress-Agent)
- [Huntress EDR pricing](https://www.huntress.com/pricing/edr)

### Microsoft Defender for Endpoint on Linux

Fit:

- usable if you already have Microsoft security licensing
- supports on-demand scanning from the command line
- less suitable if you want a fully offline, no-cloud dependency workflow

What it does:

- on-demand CLI scans
- `mdatp scan quick`
- `mdatp scan full`
- `mdatp scan custom --path`

Licensing:

- commercial
- requires one of the documented server licensing paths

Operational notes:

- strong candidate if the organization already owns Defender for Servers or Defender for Endpoint server rights
- onboarding and licensing are tied to the Defender portal and onboarding package flow

Official sources:

- [Microsoft Defender for Endpoint on Linux overview](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint-linux)
- [Configure and run antivirus scans on Linux](https://learn.microsoft.com/nb-no/defender-endpoint/configure-anti-virus-scans-linux)
- [Linux prerequisites and license requirements](https://learn.microsoft.com/en-gb/defender-endpoint/mde-linux-prerequisites)
- [Manual deployment on Linux](https://learn.microsoft.com/en-us/defender-endpoint/linux-install-manually)

### ESET Server Security for Linux

Fit:

- strong candidate for scripted one-shot scans
- better fit than Huntress for offline or semi-offline scanning workflows

What it does:

- on-demand scanning
- custom scan targets include local drives, network drives, removable media, boot sectors, and custom paths

Licensing:

- commercial
- requires an ESET license
- official docs also describe activation using an offline license file

Operational notes:

- one of the better commercial candidates for this project
- docs explicitly warn against installing multiple antivirus products on the same machine

Official sources:

- [ESET Server Security for Linux overview](https://help.eset.com/essl/12.0/en-US/)
- [ESET scans documentation](https://help.eset.com/essl/13.0/en-US/scans.html)
- [ESET activation options](https://help.eset.com/essl/12.0/en-US/activate.html)
- [ESET installation steps](https://help.eset.com/essl/13.1/en-US/installation_steps.html)

### Bitdefender Endpoint Security Tools for Linux

Fit:

- commercially viable option if Bitdefender is already in use
- supports Linux on-demand scanning

What it does:

- on-demand scanning is always available
- managed scan tasks and local/manual scan options exist

Licensing:

- commercial GravityZone licensing

Operational notes:

- viable enterprise option
- operationally more complex than `ClamAV`

Official sources:

- [Bitdefender Linux quick start and scanning notes](https://www.bitdefender.com/business/support/en/77209-157515-bitdefender-endpoint-security-tools-for-linux-quick-start-guide.html)
- [Bitdefender on-demand scanning](https://www.bitdefender.com/business/support/en/77209-342937-on-demand.html)
- [Bitdefender license management](https://www.bitdefender.com/business/support/en/77212-98153-license-management.html)

## Recommended direction

For the first PXE scanner iteration:

1. Start with `ClamAV` as the guaranteed baseline engine.
2. Add one commercial engine only after licensing is confirmed.
3. Prefer `ESET` or `Microsoft Defender` first if the business already owns licensing.
4. Treat `Huntress` as out of scope for the offline scanner image.
5. Treat `Sophos` as feasible, but commercial and likely best only when there is an existing Sophos estate.

## Recommendation for repo planning

Model the PXE client role to support engines as pluggable scan providers:

- `clamav`
- `eset`
- `defender`
- `sophos`
- `bitdefender`

Each provider should define:

- install/acquisition path
- signature update method
- scan command
- exit-code handling
- log parsing
- quarantine or copy decision behavior

## Current repo implementation status

As of Friday, July 31, 2026, the PXE client runtime currently has:

- `ClamAV` wired into freshness enforcement and offline scanning
- `YARA` wired into freshness reporting and offline scanning
- `Microsoft Defender for Endpoint`, `Sophos Protection for Linux`, and `Bitdefender Endpoint Security Tools` represented as explicit provider placeholders only

Those commercial providers now appear in the PXE client readiness metadata and splash screen as `awaiting_bundle` until a licensed installer bundle and vendor-approved offline update flow are provided.

Codex did not accept commercial license terms on the operator's behalf. That step must be completed manually by an authorized user before those bundles are staged into the repo or build pipeline.

The lab now tracks this explicitly in [inventories/lab/group_vars/all/license_acceptance.yml.example](/C:/Users/Ziggi/AV/inventories/lab/group_vars/all/license_acceptance.yml.example). Copy it locally to `inventories/lab/group_vars/all/license_acceptance.yml`, which is gitignored, then update the local file after an authorized operator accepts the relevant terms. Until a vendor entry is marked `accepted: true`, the PXE client reports that provider as `awaiting_acceptance`. Once accepted, the status moves to `awaiting_bundle` until the licensed installer payload is actually staged.
