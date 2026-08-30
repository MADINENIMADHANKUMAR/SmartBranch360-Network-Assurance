# SmartBranch 360

## Secure Branch Office Network with Cisco Packet Tracer and Python

SmartBranch 360 is a branch-office networking project that demonstrates the design, configuration, testing, troubleshooting, and automated validation of a secure small-office network using **Cisco Packet Tracer, Cisco IOS, and Python**.

---

## Project Objective

The objective of SmartBranch 360 is to design and implement a functional branch office network that provides:

- Employee network connectivity
- Guest wireless access
- Internal server connectivity
- Internet access
- DHCP and DNS services
- Inter-VLAN routing
- NAT/PAT
- Guest network isolation
- Secure network-device management using SSH
- Automated network configuration auditing using Python

---

## Network Topology

The SmartBranch 360 network consists of:
<img width="1257" height="699" alt="network-topology" src="https://github.com/user-attachments/assets/f50c7ac2-87be-44fd-96ff-53ad63624d18" />

- 1 branch router
- 2 Cisco switches
- 1 wireless access point
- 1 internal server
- 1 simulated Internet/ISP connection
- 8 endpoints

The branch router uses **Router-on-a-Stick** for inter-VLAN routing.

### VLAN and IP Addressing

| VLAN | Name | Network | Gateway |
|------|------|---------|---------|
| 10 | Employee | 10.10.10.0/24 | 10.10.10.1 |
| 20 | Guest | 10.10.20.0/24 | 10.10.20.1 |
| 30 | Server | 10.10.30.0/24 | 10.10.30.1 |
| 99 | Management | 10.10.99.0/24 | 10.10.99.1 |

---

## Network Services

The project implements the following networking services and technologies:

- VLAN segmentation
- 802.1Q trunking
- Router-on-a-Stick
- Inter-VLAN routing
- DHCP
- DHCP relay using `ip helper-address`
- DNS reachability
- NAT/PAT
- Default routing toward the simulated Internet
- Access Control Lists (ACLs)
- SSH remote management

---

## Security Design

### Guest Network Isolation

Guest users are placed in **VLAN 20**.

Guest traffic is restricted from accessing:

- Employee VLAN 10
- Server VLAN 30
- Management VLAN 99

Guest users are allowed to access the Internet.

DNS access to the internal server is permitted according to the project requirements.

### Secure Device Management

Network-device management is restricted to the **Management VLAN 99**.

The project uses:

- SSH for remote device management
- Management VLAN access control
- Telnet disabled for remote management

---

## Connectivity Requirements

The completed network is designed to satisfy the following conditions.

### Employee Traffic

Employee PCs should:

- Obtain an IP address through DHCP
- Reach the internal server
- Reach the simulated Internet

### Guest Traffic

Guest devices should:

- Obtain network connectivity
- Reach the Internet
- Be blocked from protected internal networks

### Management Traffic

The Management PC should:

- Access network devices through SSH
- Be permitted to manage network devices

Other VLANs should not be permitted to remotely manage the network devices.

---

## Troubleshooting and Fault Injection

Five intentional fault scenarios were created to demonstrate network troubleshooting.

### Fault 01 — Wrong Gateway

An incorrect gateway configuration is introduced for the Employee VLAN.

**Expected result:** Employee connectivity is affected.

**Diagnosis:** The router sub-interface address is compared with the expected gateway in the network plan.

---

### Fault 02 — Missing VLAN on Trunk

VLAN 20 is removed from the trunk's allowed VLAN list.

**Expected result:** Guest VLAN connectivity across the trunk is affected.

**Diagnosis:** `show interfaces trunk` is analyzed to determine whether VLAN 20 is allowed.

---

### Fault 03 — Bad DHCP

A DHCP relay/configuration problem is introduced.

**Expected result:** Clients may fail to obtain the expected IP configuration.

**Diagnosis:** DHCP-related configuration and captured command output are analyzed.

---

### Fault 04 — DNS / ACL Problem

An ACL configuration affecting DNS traffic is introduced.

**Expected result:** DNS communication is affected while other traffic may continue to work.

**Diagnosis:** ACL rules and their matching traffic are analyzed.

---

### Fault 05 — NAT / Internet Problem

A NAT or Internet-routing problem is introduced.

**Expected result:** Internal clients may communicate internally but fail to reach the simulated Internet.

**Diagnosis:** NAT configuration, translations, routing information, and relevant command outputs are analyzed.

---

## Python Network Assurance Tool

SmartBranch 360 includes a Python-based network assurance tool that analyzes the planned network configuration and captured Cisco IOS command outputs.

The tool uses **rule-based validation** to identify likely configuration problems.

### Inputs

The tool can use:

1. A YAML network requirement/plan file
2. Captured Cisco `show` command output

### Available Audits

The tool provides the following audit functions:

- Network plan validation
- Cisco show-output analysis
- VLAN and IP audit
- DHCP and DNS audit
- Routing audit
- NAT / Internet audit
- Security audit
- Fault diagnosis
- Full network audit
- Validation report generation

### Example Finding

```text
[FAIL] VLAN 20 (Guest) missing on trunk

Symptom:
Devices on VLAN 20 have no connectivity across the trunk link.

Evidence:
VLAN 20 does not appear in the trunk's allowed-VLAN list.

Suggested fix:
switchport trunk allowed vlan add 20

Verification:
show interfaces trunk
```

---

## Technologies Used

- Cisco Packet Tracer
- Cisco IOS
- Python 3
- YAML
- IPv4
- VLANs
- 802.1Q Trunking
- Router-on-a-Stick
- Inter-VLAN Routing
- DHCP
- DNS
- NAT/PAT
- Access Control Lists (ACLs)
- SSH

---

## Repository Structure

```text
SmartBranch360/
├── README.md
├── SmartBranch360.pkt
├── smartbranch_plan.yaml
├── network_checker.py
├── fault_cards/
├── show_outputs/
└── reports/
```

---

## How to Run the Python Tool

### Requirements

- Python 3.x
- Cisco Packet Tracer

### Run

From the project directory:

```bash
python network_checker.py
```

On Windows:

```bash
py network_checker.py
```

The Python tool provides options for network-plan validation, Cisco show-output analysis, VLAN/IP auditing, DHCP/DNS auditing, routing, NAT/Internet, security, fault diagnosis, and validation report generation.

---

## Final Validation

After resolving the configured fault scenarios, the final Python assurance run produced:

```text
NETWORK HEALTH SCORE: 100/100

PASS:            30
WARNING:          0
FAIL:             0
NOT VERIFIABLE:   0
```

The final network was verified for employee connectivity, guest isolation, Internet connectivity, secure SSH management, VLAN configuration, routing, NAT/PAT, DHCP/DNS, and the configured troubleshooting scenarios.

---

