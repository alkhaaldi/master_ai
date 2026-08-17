# CORRECTION 1 — Phase 0 was wrong about the group (2026-08-13)

**My error.** The plan said `svc-claude` should be in the `users` group only.
On Synology that account can never SSH in, no matter how correct the keys and
permissions are.

DSM restricts SSH login to members of the **administrators** group. Community
reports are consistent: the public key is accepted and the connection is then
closed immediately; moving the same user into `administrators` makes it work.
That is why `ssh nas` returned Permission denied — nothing was misconfigured.

## Chosen approach: administrators group + locked down everywhere else

The documented workaround is to put the service account in `administrators`
but strip everything else, so a compromised key cannot be used to take over
the NAS through the web interface.

USER, in DSM:
1. `Control Panel → User → svc-claude → Edit → User Groups` → add
   **administrators**
2. `→ Applications tab` → **Deny DSM**, deny everything else
   (this is the important part — no web login with this account)
3. `→ Permissions tab` → no shared folder access yet; phases grant as needed
4. `Control Panel → Security → Firewall` → allow SSH (22) from the LAN
   subnet `192.168.108.0/22` only

## Then install the key

On the RPi, one time, entering the svc-claude password once:
```bash
ssh-copy-id -i ~/.ssh/nas_svc.pub svc-claude@192.168.109.45
ssh nas "echo OK; id"
```
`id` must show the administrators group. Report both outputs.

## Standing rule

SSH on the NAS stays **off** except while a phase is actively running.
CC asks the user to enable it, works, then asks him to turn it off again.
