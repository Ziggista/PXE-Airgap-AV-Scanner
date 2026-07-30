# Platform Topology

This project uses four runtime nodes:

1. `control node`
   - Ansible runner
   - git checkout
   - operator tooling

2. `proxy node`
   - internet-facing mirror and acquisition node
   - `aptly`
   - `nginx`
   - staged AV definitions and approved artifacts

3. `pxe server node`
   - DHCP/TFTP/HTTP PXE services
   - client image build workspace
   - points upstream to the proxy node

4. `pxe client node`
   - boots from network
   - autologin minimal desktop session
   - red disconnect banner and network test
   - read-only source media handling
   - writable destination media blocked until scans succeed
