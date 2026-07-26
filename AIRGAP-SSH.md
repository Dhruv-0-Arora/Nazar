# Air-gapped SSH over direct ethernet

How to SSH into a machine with no internet, no router, no DHCP, and no DNS, using only a cable.
Useful for reaching a client machine that is offline by policy but still needs hands-on access.

## Why it works

Every IPv6 interface self-assigns a link-local `fe80::` address the moment it comes up, with no server involved.
That is the whole trick: IPv4 needs DHCP or manual configuration, IPv6 link-local needs nothing.

## Steps

### 1. Bring up the Linux side

NetworkManager marks an interface `disconnected` after DHCP times out, which strips its addresses.
Take it out of NetworkManager's hands so the link-local address survives:

```bash
sudo nmcli device set <iface> managed no
sudo ip link set <iface> up
ip -6 addr show dev <iface>          # expect an fe80:: address
```

### 2. Connect the peer

Plug the cable in and confirm the peer's ethernet interface is enabled.
macOS self-assigns both link-local addresses automatically, so nothing else is needed there.
Enable Remote Login in System Settings > General > Sharing, or run `sudo systemsetup -setremotelogin on`.

### 3. Discover the peer

```bash
ping6 -c 4 -I <iface> ff02::1%<iface>   # all-nodes multicast; replies are your neighbors
ip -6 neigh show dev <iface>            # the peer's fe80:: address and MAC
avahi-browse -rt _ssh._tcp              # confirms identity and that sshd is advertising
```

Ignore your own address in the multicast replies.
Apple MAC OUIs such as `38:7c:76` help confirm which neighbor is the Mac.

### 4. Connect

```bash
ssh <user>@fe80::<peer-addr>%<iface> '<command>'
```

The `%<iface>` scope suffix is mandatory.
A link-local address is only meaningful relative to an interface, so SSH cannot route without it.

Worked example from this project:

```bash
ssh dhruvarora@fe80::408:4412:3a20:c606%enP7s7 'printf "# hi\n" > ~/Documents/hi.md'
```

## Key auth

Password prompts are interactive and break scripted use, so install a key first:

```bash
# on the peer
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo '<your-public-key>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Then add `-o BatchMode=yes` so a failed key fails fast instead of hanging on a prompt.

## Verifying you reached the right machine

Host key fingerprints are transport-independent.
Capture them once over any network with `ssh-keyscan <host> | ssh-keygen -lf -`, then compare after switching to the cable.
Matching fingerprints prove it is the same machine even though the address changed completely.

## Gotchas

| Symptom | Cause | Fix |
| --- | --- | --- |
| Interface has no address | NetworkManager dropped it after DHCP timeout | `nmcli device set <iface> managed no` |
| `Invalid argument` on connect | Missing `%<iface>` scope suffix | Always scope link-local addresses |
| RX packet counter frozen | Nothing alive on the far end | Check the cable is seated and the peer's interface is on |
| Ping fails but port 22 answers | macOS firewall stealth mode drops ICMP | Ignore ping, test TCP instead |
| `.local` name will not resolve | `nsswitch.conf` uses `mdns4_minimal`, which is IPv4 only | Use the `fe80::` literal, or switch to `mdns` for IPv6 |
| Peer only has a `169.254.x.x` address | IPv4 link-local, unreachable without one of your own | `sudo ip addr add 169.254.100.1/16 dev <iface>` |

## Where this fits

Per ADR-0003 a direct cable is not a transport mode of its own.
It is mode 1 (`brain pull <host>`) or mode 2 (scp push) over a different link, a connectivity choice rather than an architecture choice.
Note that ADR-0003 describes this option as needing static IPs; IPv6 link-local means it does not, so no addressing needs to be agreed in advance.

## Limits

This reaches a machine on the far end of a cable, not one on a genuinely separate network.
If there is no physical path, no configuration substitutes for one.
For that case use mode 3 and `transport-layer/usb-transport/`.

Link-local addresses derive from a stable-privacy IID and can change across reboots or network resets.
Rediscover with step 3 rather than hardcoding an address into scripts.
