# Hyper-V Ubuntu VM Layout

Recommended split:

1. `av-proxy-vm`
   - Ubuntu Server LTS
   - internet egress enabled
   - hosts the proxy cache service
   - optional larger virtual disk for cached payloads and signature packages

2. `av-build-vm`
   - Ubuntu Server LTS
   - isolated PXE/build network
   - hosts PXE build logic, staged boot media, manifests, and downstream file serving
   - talks upstream only to `av-proxy-vm`

3. `pxe-client`
   - Ubuntu live boot target
   - RAM-only runtime
   - receives boot payloads from `av-build-vm`
   - scans removable media offline before writing approved content to a clean destination drive
   - mounts FAT, exFAT, and NTFS media using Linux filesystem tooling

Suggested Hyper-V approach:

- Put `av-proxy-vm` on a switch with internet access.
- Put `av-build-vm` on an internal or private virtual switch shared with the PXE segment.
- If needed, add a second NIC to `av-build-vm` for controlled management traffic.
- Publish files acquired on Windows into the Ubuntu VMs using SMB, SCP, or an attached VHDX staging disk.

Near-term next steps:

- Replace the placeholder build server with real DHCP/TFTP/iPXE services.
- Build the client boot image around Ubuntu live or a custom initramfs-based RAM environment.
- Add explicit FAT, exFAT, and NTFS handling in the client runtime with Linux tooling.
- Add a post-boot NIC disable action after policies and signatures are loaded.
