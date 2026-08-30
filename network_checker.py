#!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime
PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
NOT_VERIFIABLE = "NOT VERIFIABLE"
SCORE_PENALTY = {
    PASS: 0,
    WARNING: 5,
    NOT_VERIFIABLE: 2,
    FAIL: 12,
}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLAN_FILE = os.path.join(BASE_DIR, "smartbranch_plan.yaml")
DEFAULT_SHOW_DIR = os.path.join(BASE_DIR, "show_outputs")
DEFAULT_REPORT_FILE = os.path.join(
    BASE_DIR, "reports", "validation_report.txt"
)
class Finding:
    def __init__(
        self,
        status,
        category,
        title,
        symptom=None,
        evidence=None,
        root_cause=None,
        fix=None,
        verify=None,
        confidence=None,
    ):
        self.status = status
        self.category = category
        self.title = title
        self.symptom = symptom
        self.evidence = evidence
        self.root_cause = root_cause
        self.fix = fix
        self.verify = verify
        self.confidence = confidence
    def has_diagnostics(self):
        return any(
            [
                self.symptom,
                self.evidence,
                self.root_cause,
                self.fix,
                self.verify,
            ]
        )
    def as_lines(self):
        lines = [f"[{self.status}] {self.title}"]
        if self.has_diagnostics():
            if self.symptom:
                lines.extend(["  Symptom:", f"    {self.symptom}"])
            if self.evidence:
                lines.extend(["  Evidence:", f"    {self.evidence}"])
            if self.root_cause:
                lines.extend(
                    ["  Likely root cause:", f"    {self.root_cause}"]
                )
            if self.fix:
                lines.extend(["  Suggested fix:", f"    {self.fix}"])
            if self.verify:
                lines.append("  Verification command(s):")
                commands = (
                    self.verify
                    if isinstance(self.verify, list)
                    else [self.verify]
                )
                for command in commands:
                    lines.append(f"    {command}")
            if self.confidence:
                lines.append(f"  Confidence: {self.confidence}")
        return lines
def parse_simple_yaml(text):
    root = {}
    stack = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        if ":" not in content:
            continue
        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            new_dict = {}
            parent[key] = new_dict
            stack.append((indent, new_dict))
        else:
            parent[key] = _convert_scalar(value)
    return root
def _convert_scalar(value):
    lowered = value.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in "\"'"
    ):
        return value[1:-1]
    return value
def load_plan(path):
    if not os.path.isfile(path):
        return None, f"Plan file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except OSError as exc:
        return None, f"Could not read plan file: {exc}"
    try:
        return parse_simple_yaml(text), None
    except Exception as exc:
        return None, f"Could not parse plan file: {exc}"
COMMAND_PROMPT_RE = re.compile(r"^(\S+)#\s*(show\s+.+)$", re.IGNORECASE)
def parse_show_outputs(text):
    result = {}
    current_device = None
    current_command = None
    buffer = []
    def flush():
        if current_device and current_command:
            result.setdefault(current_device, {})
            result[current_device][current_command] = "\n".join(
                buffer
            ).strip()
    for line in text.splitlines():
        match = COMMAND_PROMPT_RE.match(line.strip())
        if match:
            flush()
            current_device = match.group(1)
            current_command = match.group(2).strip()
            buffer = []
        else:
            buffer.append(line)
    flush()
    return result
def load_show_outputs(path):
    if not os.path.isfile(path):
        return None, f"Show-output file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except OSError as exc:
        return None, f"Could not read show-output file: {exc}"
    if not text.strip():
        return {}, "Show-output file is empty."
    parsed = parse_show_outputs(text)
    if not parsed:
        return (
            {},
            "No recognizable 'HOSTNAME#show ...' command lines were found.",
        )
    return parsed, None
def find_all(parsed, keyword):
    keyword = keyword.lower()
    matches = []
    for device, commands in parsed.items():
        for command, output in commands.items():
            if keyword in command.lower():
                matches.append((device, command, output))
    return matches
def combined_text(parsed, keyword=None):
    if keyword is None:
        outputs = [
            output
            for device in parsed.values()
            for output in device.values()
        ]
    else:
        outputs = [
            output
            for _, _, output in find_all(parsed, keyword)
        ]
    return "\n".join(outputs)
def whole_capture_text(parsed):
    return combined_text(parsed)
def parse_running_config_interfaces(config_text):
    blocks = {}
    current = None
    buffer = []
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^interface\s+(\S+)", line, re.IGNORECASE)
        if match:
            if current is not None:
                blocks[current] = buffer
            current = match.group(1)
            buffer = []
        elif line == "!":
            if current is not None:
                blocks[current] = buffer
                current = None
                buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        blocks[current] = buffer
    return blocks
def parse_vlan_brief(vlan_text):
    vlans = {}
    for line in vlan_text.splitlines():
        match = re.match(
            r"^(\d+)\s+(\S+)\s+(\S+)",
            line.strip(),
        )
        if match:
            vlan_id = int(match.group(1))
            vlans[vlan_id] = {
                "name": match.group(2),
                "status": match.group(3),
            }
    return vlans
def parse_trunk_allowed_vlans(trunk_text):
    allowed = set()
    for line in trunk_text.splitlines():
        stripped = line.strip()
        match = re.match(
            r"^\S+\s+([\d,\-]+)\s*$",
            stripped,
        )
        if not match:
            continue
        for chunk in match.group(1).split(","):
            chunk = chunk.strip()
            if "-" in chunk:
                try:
                    start, end = chunk.split("-", 1)
                    allowed.update(
                        range(int(start), int(end) + 1)
                    )
                except ValueError:
                    continue
            elif chunk.isdigit():
                allowed.add(int(chunk))
    return allowed
def parse_ip_int_brief(int_brief_text):
    interfaces = {}
    for line in int_brief_text.splitlines():
        tokens = line.split()
        if len(tokens) < 5:
            continue
        if tokens[0].lower() == "interface":
            continue
        name = tokens[0]
        ip = tokens[1]
        if "administratively" in tokens:
            status = "administratively down"
            protocol = tokens[-1]
        else:
            status = tokens[-2]
            protocol = tokens[-1]
        interfaces[name] = {
            "ip": ip,
            "status": status,
            "protocol": protocol,
        }
    return interfaces
def parse_ip_route(route_text):
    has_default = bool(
        re.search(
            r"^\s*S\*?\s+0\.0\.0\.0/0",
            route_text,
            re.MULTILINE,
        )
    )
    gateway_set = (
        "gateway of last resort is not set"
        not in route_text.lower()
    )
    return {
        "has_default_route": has_default and gateway_set
    }
def parse_nat_statistics(nat_text):
    match = re.search(
        r"Total\s+(?:active\s+)?translations:\s*(\d+)",
        nat_text,
        re.IGNORECASE,
    )
    translations = int(match.group(1)) if match else None
    return {"translations": translations}
def find_helper_address(interface_lines):
    for line in interface_lines:
        match = re.match(
            r"^ip helper-address\s+(\S+)",
            line.strip(),
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
    return None
def find_access_group(interface_lines):
    for line in interface_lines:
        match = re.match(
            r"^ip access-group\s+(\S+)\s+(in|out)",
            line.strip(),
            re.IGNORECASE,
        )
        if match:
            return match.group(1), match.group(2)
    return None, None
def extract_acl_entries(acl_text):
    entries = []
    current_num = None
    for raw_line in acl_text.splitlines():
        line = raw_line.strip()
        match = re.match(
            r"^access-list\s+(\S+)\s+(?:deny|permit)\s+.+",
            line,
            re.IGNORECASE,
        )
        if match:
            entries.append((match.group(1), line))
            continue
        match = re.match(
            r"^(?:Standard|Extended)\s+IP access list\s+(\S+)",
            line,
            re.IGNORECASE,
        )
        if match:
            current_num = match.group(1)
            continue
        match = re.match(
            r"^\d+\s+(?:deny|permit)\s+.+",
            line,
            re.IGNORECASE,
        )
        if match and current_num:
            entries.append((current_num, line))
    return entries
def get_applied_acl_numbers(interface_blocks):
    applied = set()
    for lines in interface_blocks.values():
        acl_number, _ = find_access_group(lines)
        if acl_number:
            applied.add(acl_number)
    return applied
def acl_lines_between(
    subnet_a,
    subnet_b,
    acl_text,
    applied_only=None,
):
    hits = []
    for acl_number, line in extract_acl_entries(acl_text):
        lower = line.lower()
        if "deny" not in lower:
            continue
        if subnet_a not in line or subnet_b not in line:
            continue
        if (
            applied_only is not None
            and acl_number not in applied_only
        ):
            continue
        hits.append(line)
    return hits
def acl_lines_blocking_dns(
    server_ip,
    acl_text,
    applied_only=None,
):
    hits = []
    for acl_number, line in extract_acl_entries(acl_text):
        lower = line.lower()
        if "deny" not in lower:
            continue
        if server_ip not in line:
            continue
        if "eq 53" not in lower and "domain" not in lower:
            continue
        if (
            applied_only is not None
            and acl_number not in applied_only
        ):
            continue
        hits.append(line)
    return hits
def get_vlan_plan(plan):
    vlans = plan.get("vlans", {}) if isinstance(plan, dict) else {}
    normalized = {}
    for key, info in vlans.items():
        try:
            vlan_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(info, dict):
            normalized[vlan_id] = info
    return normalized
def _find_subinterface(interfaces, vlan_id):
    suffix = f".{vlan_id}"
    for name in interfaces:
        if name.endswith(suffix):
            return name
    return None
def audit_vlan_ip(plan, parsed):
    findings = []
    category = "VLAN & IP"
    vlans = get_vlan_plan(plan)
    if not vlans:
        return [
            Finding(
                NOT_VERIFIABLE,
                category,
                "No VLANs defined in the plan.",
            )
        ]
    vlan_matches = find_all(parsed, "vlan brief")
    if not vlan_matches:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show vlan brief' output supplied.",
                verify="show vlan brief",
            )
        )
    else:
        switch_vlans = {}
        for _, _, text in vlan_matches:
            switch_vlans.update(parse_vlan_brief(text))
        for vlan_id, info in sorted(vlans.items()):
            expected_name = info.get("name", "")
            if vlan_id not in switch_vlans:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        f"VLAN {vlan_id} ({expected_name}) not found on any switch",
                        symptom=(
                            f"Devices intended for VLAN {vlan_id} "
                            "cannot connect correctly."
                        ),
                        evidence=(
                            f"VLAN {vlan_id} does not appear in "
                            "'show vlan brief'."
                        ),
                        root_cause=(
                            "The VLAN was never created or was deleted."
                        ),
                        fix=(
                            f"vlan {vlan_id}\n"
                            f"name {expected_name}"
                        ),
                        verify="show vlan brief",
                        confidence="HIGH",
                    )
                )
                continue
            found = switch_vlans[vlan_id]
            if found["status"].lower() != "active":
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        (
                            f"VLAN {vlan_id} ({expected_name}) "
                            "exists but is not active"
                        ),
                        symptom=(
                            f"Devices on VLAN {vlan_id} "
                            "may be unable to communicate."
                        ),
                        evidence=(
                            f"VLAN {vlan_id} has status "
                            f"'{found['status']}'."
                        ),
                        root_cause=(
                            "The VLAN may be shutdown or not fully configured."
                        ),
                        fix=f"vlan {vlan_id}\nno shutdown",
                        verify="show vlan brief",
                        confidence="MEDIUM",
                    )
                )
            else:
                findings.append(
                    Finding(
                        PASS,
                        category,
                        (
                            f"VLAN {vlan_id} {expected_name} "
                            "detected and active"
                        ),
                    )
                )
    trunk_matches = find_all(parsed, "interfaces trunk")
    if not trunk_matches:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show interfaces trunk' output supplied.",
                verify="show interfaces trunk",
            )
        )
    else:
        allowed = set()
        for _, _, text in trunk_matches:
            allowed.update(
                parse_trunk_allowed_vlans(text)
            )
        for vlan_id, info in sorted(vlans.items()):
            name = info.get("name", "")
            if vlan_id in allowed:
                findings.append(
                    Finding(
                        PASS,
                        category,
                        f"VLAN {vlan_id} {name} is allowed on the trunk",
                    )
                )
            else:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        f"VLAN {vlan_id} ({name}) missing on trunk",
                        symptom=(
                            f"VLAN {vlan_id} traffic cannot cross "
                            "the trunk link."
                        ),
                        evidence=(
                            f"VLAN {vlan_id} is not present in the "
                            "allowed-VLAN list."
                        ),
                        root_cause=(
                            "The VLAN was removed from or never added "
                            "to the trunk."
                        ),
                        fix=(
                            f"switchport trunk allowed vlan add {vlan_id}"
                        ),
                        verify="show interfaces trunk",
                        confidence="HIGH",
                    )
                )
    interface_matches = find_all(parsed, "ip interface brief")
    if not interface_matches:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show ip interface brief' output supplied.",
                verify="show ip interface brief",
            )
        )
    else:
        interfaces = {}
        for _, _, text in interface_matches:
            interfaces.update(
                parse_ip_int_brief(text)
            )
        for vlan_id, info in sorted(vlans.items()):
            expected_gateway = info.get("gateway")
            name = info.get("name", "")
            subinterface = _find_subinterface(
                interfaces,
                vlan_id,
            )
            if subinterface is None:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        (
                            f"No router subinterface found for "
                            f"VLAN {vlan_id} ({name})"
                        ),
                        symptom=(
                            f"Devices on VLAN {vlan_id} "
                            "have no default gateway."
                        ),
                        evidence=(
                            f"No interface ending in '.{vlan_id}' "
                            "was found."
                        ),
                        root_cause=(
                            "The router-on-a-stick subinterface "
                            "was not created."
                        ),
                        fix=(
                            f"interface GigabitEthernet0/1.{vlan_id}\n"
                            f"encapsulation dot1Q {vlan_id}\n"
                            f"ip address {expected_gateway} <subnet-mask>"
                        ),
                        verify="show ip interface brief",
                        confidence="HIGH",
                    )
                )
                continue
            data = interfaces[subinterface]
            if (
                "down" in data["status"].lower()
                or "down" in data["protocol"].lower()
            ):
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        (
                            f"Interface {subinterface} "
                            f"for VLAN {vlan_id} is down"
                        ),
                        symptom=(
                            f"VLAN {vlan_id} cannot reach its gateway."
                        ),
                        evidence=(
                            f"{subinterface} status is "
                            f"'{data['status']}', protocol is "
                            f"'{data['protocol']}'."
                        ),
                        root_cause=(
                            "The subinterface, parent interface, "
                            "or trunk may be down."
                        ),
                        fix=(
                            f"Check {subinterface} and its parent "
                            "interface; use 'no shutdown'."
                        ),
                        verify="show ip interface brief",
                        confidence="HIGH",
                    )
                )
            elif expected_gateway and data["ip"] != expected_gateway:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        f"Wrong gateway detected for VLAN {vlan_id}",
                        symptom=(
                            f"Devices on VLAN {vlan_id} may have "
                            "connectivity problems."
                        ),
                        evidence=(
                            f"Expected {expected_gateway} on "
                            f"{subinterface}, found {data['ip']}."
                        ),
                        root_cause=(
                            "The subinterface IP address does not "
                            "match the network design."
                        ),
                        fix=(
                            f"ip address {expected_gateway} "
                            "<subnet-mask>"
                        ),
                        verify="show ip interface brief",
                        confidence="HIGH",
                    )
                )
            else:
                findings.append(
                    Finding(
                        PASS,
                        category,
                        (
                            f"VLAN {vlan_id} gateway correct on "
                            f"{subinterface}"
                        ),
                    )
                )
    return findings
def audit_dhcp_dns(plan, parsed):
    findings = []
    category = "DHCP & DNS"
    services = plan.get("services", {})
    server = plan.get("server", {})
    server_ip = server.get("ip")
    vlans = get_vlan_plan(plan)
    run_configs = find_all(parsed, "running-config")
    full_configs = [
        text
        for _, command, text in run_configs
        if "section" not in command.lower()
    ]
    if services.get("dhcp_relay", True):
        if not full_configs:
            findings.append(
                Finding(
                    NOT_VERIFIABLE,
                    category,
                    "No full 'show running-config' supplied for DHCP relay.",
                    verify="show running-config",
                )
            )
        elif not server_ip:
            findings.append(
                Finding(
                    NOT_VERIFIABLE,
                    category,
                    "Server IP is missing from the network plan.",
                )
            )
        else:
            combined_config = "\n".join(full_configs)
            interface_blocks = parse_running_config_interfaces(
                combined_config
            )
            for vlan_id, info in sorted(vlans.items()):
                name = info.get("name", "")
                interface = _find_subinterface(
                    interface_blocks,
                    vlan_id,
                )
                if interface is None:
                    findings.append(
                        Finding(
                            NOT_VERIFIABLE,
                            category,
                            (
                                f"No running-config interface found "
                                f"for VLAN {vlan_id}."
                            ),
                        )
                    )
                    continue
                helper = find_helper_address(
                    interface_blocks[interface]
                )
                if helper is None:
                    findings.append(
                        Finding(
                            FAIL,
                            category,
                            (
                                f"DHCP relay missing on VLAN "
                                f"{vlan_id} ({name})"
                            ),
                            symptom=(
                                f"Clients on VLAN {vlan_id} may not "
                                "receive DHCP addresses."
                            ),
                            evidence=(
                                f"No ip helper-address found under "
                                f"{interface}."
                            ),
                            root_cause=(
                                "DHCP relay was not configured "
                                "on the subinterface."
                            ),
                            fix=(
                                f"interface {interface}\n"
                                f"ip helper-address {server_ip}"
                            ),
                            verify="show running-config",
                            confidence="HIGH",
                        )
                    )
                elif helper != server_ip:
                    findings.append(
                        Finding(
                            FAIL,
                            category,
                            (
                                f"DHCP relay on VLAN {vlan_id} "
                                "points to the wrong server"
                            ),
                            symptom=(
                                f"Clients on VLAN {vlan_id} may not "
                                "receive a DHCP lease."
                            ),
                            evidence=(
                                f"Expected {server_ip}, found {helper}."
                            ),
                            root_cause=(
                                "The configured DHCP relay address "
                                "does not match the server."
                            ),
                            fix=(
                                f"no ip helper-address {helper}\n"
                                f"ip helper-address {server_ip}"
                            ),
                            verify="show running-config",
                            confidence="HIGH",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            PASS,
                            category,
                            (
                                f"DHCP relay on VLAN {vlan_id} "
                                f"points to {server_ip}"
                            ),
                        )
                    )
    binding_matches = find_all(parsed, "dhcp binding")
    if binding_matches:
        binding_text = binding_matches[0][2]
        no_bindings = (
            re.search(
                r"\btotal number of clients:\s*0\b",
                binding_text,
                re.IGNORECASE,
            )
            or "no bindings found" in binding_text.lower()
        )
        if no_bindings:
            findings.append(
                Finding(
                    WARNING,
                    category,
                    "No active DHCP bindings observed",
                    symptom="No client currently holds a DHCP lease.",
                    evidence="DHCP binding output reports zero clients.",
                    root_cause=(
                        "No client may have requested an address, "
                        "or DHCP may have another problem."
                    ),
                    fix=(
                        "Renew DHCP on a client and run "
                        "'show ip dhcp binding' again."
                    ),
                    verify="show ip dhcp binding",
                    confidence="LOW",
                )
            )
        else:
            findings.append(
                Finding(
                    PASS,
                    category,
                    "DHCP bindings observed for clients",
                )
            )
    else:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show ip dhcp binding' output supplied.",
                verify="show ip dhcp binding",
            )
        )
    if services.get("dns", True):
        if server_ip and server_ip in whole_capture_text(parsed):
            findings.append(
                Finding(
                    PASS,
                    category,
                    (
                        f"DNS server address {server_ip} "
                        "appears in captured configuration/output"
                    ),
                )
            )
        else:
            dns_name = server.get(
                "dns_name",
                "server.smartbranch.local",
            )
            findings.append(
                Finding(
                    NOT_VERIFIABLE,
                    category,
                    "DNS server operation could not be confirmed.",
                    evidence=(
                        f"Server IP {server_ip or '(not configured)'} "
                        "was not found in the captured output."
                    ),
                    root_cause=(
                        "Router show commands cannot directly prove "
                        "that the DNS service itself is operational."
                    ),
                    fix=(
                        f"Verify from a client using: "
                        f"nslookup {dns_name}"
                    ),
                    confidence="LOW",
                )
            )
    return findings
def audit_routing(plan, parsed):
    findings = []
    category = "Routing"
    vlans = get_vlan_plan(plan)
    interface_matches = find_all(parsed, "ip interface brief")
    if not interface_matches:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show ip interface brief' output supplied.",
                verify="show ip interface brief",
            )
        )
    else:
        interfaces = {}
        for _, _, text in interface_matches:
            interfaces.update(
                parse_ip_int_brief(text)
            )
        missing = [
            vlan_id
            for vlan_id in vlans
            if _find_subinterface(interfaces, vlan_id) is None
        ]
        if missing:
            findings.append(
                Finding(
                    FAIL,
                    category,
                    "Router-on-a-stick subinterfaces are incomplete",
                    symptom=(
                        "Some VLANs cannot route to other VLANs "
                        "or the internet."
                    ),
                    evidence=(
                        "Missing VLAN subinterfaces: "
                        + ", ".join(map(str, sorted(missing)))
                    ),
                    root_cause=(
                        "One or more VLAN subinterfaces "
                        "were not configured."
                    ),
                    fix=(
                        "Create the missing "
                        "GigabitEthernet0/1.<vlan> subinterfaces."
                    ),
                    verify="show ip interface brief",
                    confidence="HIGH",
                )
            )
        else:
            findings.append(
                Finding(
                    PASS,
                    category,
                    "Router-on-a-stick subinterfaces detected for all VLANs",
                )
            )
    route_matches = find_all(parsed, "ip route")
    if not route_matches:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show ip route' output supplied.",
                verify="show ip route",
            )
        )
    else:
        route_info = parse_ip_route(route_matches[0][2])
        if route_info["has_default_route"]:
            findings.append(
                Finding(
                    PASS,
                    category,
                    "Default route (0.0.0.0/0) is present",
                )
            )
        else:
            findings.append(
                Finding(
                    FAIL,
                    category,
                    "Default route is missing",
                    symptom=(
                        "Internal networks may work, but internet "
                        "connectivity will fail."
                    ),
                    evidence=(
                        "No 0.0.0.0/0 route was detected."
                    ),
                    root_cause=(
                        "No default route points toward the ISP."
                    ),
                    fix=(
                        "ip route 0.0.0.0 0.0.0.0 "
                        "<ISP-next-hop-IP>"
                    ),
                    verify="show ip route",
                    confidence="HIGH",
                )
            )
    return findings
def audit_nat(plan, parsed):
    findings = []
    category = "NAT / Internet"
    services = plan.get("services", {})
    if not services.get("nat", True):
        return findings
    run_configs = find_all(parsed, "running-config")
    full_configs = [
        text
        for _, command, text in run_configs
        if "section" not in command.lower()
    ]
    combined_config = "\n".join(full_configs)
    nat_configured = False
    if not full_configs:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No full 'show running-config' supplied for NAT.",
                verify="show running-config",
            )
        )
    else:
        nat_pat = re.search(
            r"^ip nat inside source list \d+ "
            r"interface \S+ overload",
            combined_config,
            re.MULTILINE,
        )
        if nat_pat:
            nat_configured = True
            findings.append(
                Finding(
                    PASS,
                    category,
                    "PAT overload configuration detected",
                )
            )
        else:
            findings.append(
                Finding(
                    FAIL,
                    category,
                    "PAT overload configuration not detected",
                    symptom=(
                        "Internal hosts may not reach the internet."
                    ),
                    evidence=(
                        "No NAT overload command was found."
                    ),
                    root_cause=(
                        "PAT may not have been configured."
                    ),
                    fix=(
                        "ip nat inside source list 1 "
                        "interface GigabitEthernet0/0 overload"
                    ),
                    verify="show running-config",
                    confidence="HIGH",
                )
            )
        interface_blocks = parse_running_config_interfaces(
            combined_config
        )
        outside_interfaces = [
            name
            for name, lines in interface_blocks.items()
            if any(
                line.lower() == "ip nat outside"
                for line in lines
            )
        ]
        inside_interfaces = [
            name
            for name, lines in interface_blocks.items()
            if any(
                line.lower() == "ip nat inside"
                for line in lines
            )
        ]
        if outside_interfaces:
            findings.append(
                Finding(
                    PASS,
                    category,
                    (
                        "NAT outside configured on "
                        + ", ".join(outside_interfaces)
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    WARNING,
                    category,
                    "No interface marked 'ip nat outside'",
                    evidence=(
                        "No interface contains 'ip nat outside'."
                    ),
                    root_cause=(
                        "The WAN interface may be missing the command."
                    ),
                    fix="Add 'ip nat outside' to the WAN interface.",
                    verify="show running-config",
                    confidence="MEDIUM",
                )
            )
        if inside_interfaces:
            findings.append(
                Finding(
                    PASS,
                    category,
                    (
                        f"NAT inside configured on "
                        f"{len(inside_interfaces)} interface(s)"
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    WARNING,
                    category,
                    "No interface marked 'ip nat inside'",
                    evidence=(
                        "No inside interface was detected."
                    ),
                    root_cause=(
                        "The VLAN subinterfaces may be missing "
                        "'ip nat inside'."
                    ),
                    fix=(
                        "Add 'ip nat inside' to the inside "
                        "VLAN interfaces."
                    ),
                    verify="show running-config",
                    confidence="MEDIUM",
                )
            )
    route_matches = find_all(parsed, "ip route")
    has_default_route = False
    if route_matches:
        has_default_route = parse_ip_route(
            route_matches[0][2]
        )["has_default_route"]
    nat_stats = find_all(parsed, "nat statistics")
    if not nat_stats:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No 'show ip nat statistics' output supplied.",
                verify="show ip nat statistics",
            )
        )
    else:
        stats = parse_nat_statistics(nat_stats[0][2])
        translations = stats["translations"]

        if translations is None:
            findings.append(
                Finding(
                    NOT_VERIFIABLE,
                    category,
                    "Could not determine the NAT translation count.",
                )
            )
        elif translations == 0:
            status = (
                FAIL
                if not has_default_route or not nat_configured
                else WARNING
            )
            findings.append(
                Finding(
                    status,
                    category,
                    "No active NAT translations observed",
                    symptom=(
                        "No current NAT sessions are being translated."
                    ),
                    evidence=(
                        "'show ip nat statistics' reports "
                        "zero active translations."
                    ),
                    root_cause=(
                        "Possible causes include missing default route, "
                        "missing NAT configuration, no outside traffic, "
                        "or an incorrect NAT ACL."
                    ),
                    fix=(
                        "Check the default route and NAT configuration, "
                        "then generate traffic such as 'ping 8.8.8.8'."
                    ),
                    verify=[
                        "show ip route",
                        "show ip nat statistics",
                        "ping 8.8.8.8",
                    ],
                    confidence="MEDIUM",
                )
            )
        else:
            findings.append(
                Finding(
                    PASS,
                    category,
                    (
                        f"NAT is actively translating "
                        f"({translations} translations)"
                    ),
                )
            )
    return findings
def _extract_vty_section(config_text):
    lines = config_text.splitlines()
    output = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("line vty"):
            capturing = True
            output.append(stripped)
            continue
        if capturing:
            if (
                stripped == "!"
                or (
                    stripped.startswith("line ")
                    and not stripped.startswith("line vty")
                )
            ):
                capturing = False
                continue
            output.append(stripped)
    return "\n".join(output)
def audit_security(plan, parsed):
    findings = []
    category = "Security"
    security = plan.get("security", {})
    server = plan.get("server", {})
    server_ip = server.get("ip")
    run_configs = find_all(parsed, "running-config")
    full_configs = [
        text
        for _, command, text in run_configs
        if "section" not in command.lower()
    ]
    acl_show_matches = find_all(parsed, "access-list")
    acl_text = "\n".join(
        [text for _, _, text in acl_show_matches]
        + full_configs
    )
    guest_subnet = None
    server_subnet = None
    management_subnet = None
    for vlan_id, info in get_vlan_plan(plan).items():
        name = (info.get("name") or "").lower()
        subnet = info.get("subnet", "").split("/")[0]
        if not subnet:
            continue
        prefix = subnet.rsplit(".", 1)[0]
        if name == "guest":
            guest_subnet = prefix
        elif name == "server":
            server_subnet = prefix
        elif name == "management":
            management_subnet = prefix
    interface_blocks = (
        parse_running_config_interfaces(
            "\n".join(full_configs)
        )
        if full_configs
        else {}
    )
    applied_acls = (
        get_applied_acl_numbers(interface_blocks)
        if interface_blocks
        else None
    )
    if not acl_show_matches and not full_configs:
        findings.append(
            Finding(
                NOT_VERIFIABLE,
                category,
                "No ACL or running-config output supplied.",
                verify="show access-lists",
            )
        )
    else:
        if security.get("guest_block_server", True):
            if guest_subnet and server_subnet:
                hits = acl_lines_between(
                    guest_subnet,
                    server_subnet,
                    acl_text,
                    applied_acls,
                )
                if hits:
                    findings.append(
                        Finding(
                            PASS,
                            category,
                            "Guest-to-Server isolation ACL detected",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            FAIL,
                            category,
                            "Guest-to-Server isolation ACL not detected",
                            symptom=(
                                "Guest devices may be able to "
                                "reach the server network."
                            ),
                            evidence=(
                                f"No deny rule was found between "
                                f"{guest_subnet}.0/24 and "
                                f"{server_subnet}.0/24."
                            ),
                            root_cause=(
                                "The isolation ACL may not exist "
                                "or may not be applied."
                            ),
                            fix=(
                                f"Create an extended ACL denying "
                                f"{guest_subnet}.0/24 to "
                                f"{server_subnet}.0/24."
                            ),
                            verify="show access-lists",
                            confidence="HIGH",
                        )
                    )
        if security.get("guest_block_management", True):
            if guest_subnet and management_subnet:
                hits = acl_lines_between(
                    guest_subnet,
                    management_subnet,
                    acl_text,
                    applied_acls,
                )
                if hits:
                    findings.append(
                        Finding(
                            PASS,
                            category,
                            "Guest-to-Management isolation ACL detected",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            FAIL,
                            category,
                            "Guest-to-Management isolation ACL not detected",
                            symptom=(
                                "Guest devices may be able to "
                                "reach management infrastructure."
                            ),
                            evidence=(
                                f"No deny rule was found between "
                                f"{guest_subnet}.0/24 and "
                                f"{management_subnet}.0/24."
                            ),
                            root_cause=(
                                "The management isolation ACL may "
                                "not exist or may not be applied."
                            ),
                            fix=(
                                f"Create an ACL denying "
                                f"{guest_subnet}.0/24 to "
                                f"{management_subnet}.0/24."
                            ),
                            verify="show access-lists",
                            confidence="HIGH",
                        )
                    )
        if full_configs:
            guest_vlan_id = None
            for vlan_id, info in get_vlan_plan(plan).items():
                if (
                    (info.get("name") or "").lower()
                    == "guest"
                ):
                    guest_vlan_id = vlan_id
                    break
            if guest_vlan_id is not None:
                guest_interface = _find_subinterface(
                    interface_blocks,
                    guest_vlan_id,
                )
                if guest_interface:
                    acl_number, direction = find_access_group(
                        interface_blocks[guest_interface]
                    )
                    if acl_number:
                        findings.append(
                            Finding(
                                PASS,
                                category,
                                (
                                    f"Guest isolation ACL {acl_number} "
                                    f"is applied to {guest_interface} "
                                    f"({direction})"
                                ),
                            )
                        )
                    else:
                        findings.append(
                            Finding(
                                WARNING,
                                category,
                                (
                                    "Guest isolation ACL may exist "
                                    "but is not applied"
                                ),
                                evidence=(
                                    f"No access-group was found on "
                                    f"{guest_interface}."
                                ),
                                root_cause=(
                                    "An ACL may exist but was not "
                                    "applied to the interface."
                                ),
                                fix=(
                                    f"ip access-group "
                                    "<acl-number> in"
                                ),
                                verify="show running-config",
                                confidence="MEDIUM",
                            )
                        )
        if server_ip:
            dns_hits = acl_lines_blocking_dns(
                server_ip,
                acl_text,
                applied_acls,
            )
            if dns_hits:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        "DNS traffic may be blocked by an ACL",
                        symptom=(
                            "Clients may be unable to resolve "
                            "DNS names."
                        ),
                        evidence=(
                            f"ACL rule affecting DNS to {server_ip}: "
                            f"{dns_hits[0]}"
                        ),
                        root_cause=(
                            "An applied ACL may be denying DNS "
                            "traffic to the server."
                        ),
                        fix=(
                            f"Review the ACL and permit DNS traffic "
                            f"to {server_ip} on UDP/TCP port 53."
                        ),
                        verify="show access-lists",
                        confidence="HIGH",
                    )
                )
            else:
                findings.append(
                    Finding(
                        PASS,
                        category,
                        "No ACL rule found blocking DNS to the server",
                    )
                )
    if security.get("ssh_management_only", True):
        vty_matches = find_all(parsed, "line vty")
        if vty_matches:
            vty_text = "\n".join(
                text for _, _, text in vty_matches
            )
        elif full_configs:
            vty_text = _extract_vty_section(
                "\n".join(full_configs)
            )
        else:
            vty_text = None
        if not vty_text:
            findings.append(
                Finding(
                    NOT_VERIFIABLE,
                    category,
                    "No vty configuration supplied.",
                    verify="show running-config | section line vty",
                )
            )
        else:
            access_class = re.search(
                r"access-class\s+(\S+)\s+in",
                vty_text,
                re.IGNORECASE,
            )
            transport = re.search(
                r"transport input\s+(.+)",
                vty_text,
                re.IGNORECASE,
            )
            if access_class:
                acl_number = access_class.group(1)
                management_allowed = False
                if management_subnet:
                    for line in acl_text.splitlines():
                        lower = line.lower()
                        if (
                            acl_number in line
                            and "permit" in lower
                            and management_subnet in line
                        ):
                            management_allowed = True
                            break
                if management_allowed:
                    findings.append(
                        Finding(
                            PASS,
                            category,
                            (
                                f"SSH access is restricted by "
                                f"ACL {acl_number} for Management"
                            ),
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            WARNING,
                            category,
                            (
                                "SSH access-class exists but "
                                "Management-only access could not "
                                "be confirmed"
                            ),
                            evidence=(
                                f"vty uses access-class "
                                f"{acl_number}, but a matching "
                                "Management permit was not found."
                            ),
                            root_cause=(
                                "The ACL may be incomplete or "
                                "the required ACL output was not supplied."
                            ),
                            fix=(
                                f"Verify ACL {acl_number} permits "
                                f"{management_subnet or 'Management'} "
                                "and denies unwanted sources."
                            ),
                            verify="show access-lists",
                            confidence="LOW",
                        )
                    )
            else:
                findings.append(
                    Finding(
                        FAIL,
                        category,
                        "SSH access-class is missing from vty lines",
                        symptom=(
                            "SSH management may be reachable "
                            "from unintended VLANs."
                        ),
                        evidence=(
                            "No 'access-class <n> in' was found."
                        ),
                        root_cause=(
                            "The vty lines were not restricted."
                        ),
                        fix=(
                            "Under line vty: "
                            "access-class <management-acl> in"
                        ),
                        verify=(
                            "show running-config | section line vty"
                        ),
                        confidence="HIGH",
                    )
                )
            if transport:
                protocols = transport.group(1).lower()
                if "telnet" in protocols:
                    findings.append(
                        Finding(
                            FAIL,
                            category,
                            "Telnet is enabled on vty lines",
                            symptom=(
                                "Unencrypted Telnet management "
                                "is permitted."
                            ),
                            evidence=(
                                f"transport input "
                                f"{transport.group(1).strip()}"
                            ),
                            root_cause=(
                                "Telnet was not disabled."
                            ),
                            fix="transport input ssh",
                            verify=(
                                "show running-config | "
                                "section line vty"
                            ),
                            confidence="HIGH",
                        )
                    )
                elif "ssh" in protocols:
                    findings.append(
                        Finding(
                            PASS,
                            category,
                            "Only SSH is allowed on vty lines",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            WARNING,
                            category,
                            (
                                "Unexpected vty transport configuration"
                            ),
                            evidence=(
                                f"transport input "
                                f"{transport.group(1).strip()}"
                            ),
                        )
                    )
            else:
                findings.append(
                    Finding(
                        NOT_VERIFIABLE,
                        category,
                        "No 'transport input' line found.",
                        verify=(
                            "show running-config | "
                            "section line vty"
                        ),
                    )
                )
    else:
        findings.append(
            Finding(
                PASS,
                category,
                "SSH management restriction is not required by the plan",
            )
        )
    if not security.get("telnet_disabled", True):
        findings.append(
            Finding(
                PASS,
                category,
                "Telnet-disabled requirement is not enabled in the plan",
            )
        )
    return findings
def compute_score(findings):
    score = 100
    for finding in findings:
        score -= SCORE_PENALTY.get(
            finding.status,
            0,
        )
    return max(0, min(100, score))
def print_findings(findings, out=None):
    writer = out.write if out else print
    for finding in findings:
        for line in finding.as_lines():
            if out:
                writer(line + "\n")
            else:
                writer(line)
        if out:
            out.write("\n")
def print_section(title, findings, out=None):
    header = title.upper()
    separator = "-" * 50
    if out:
        out.write(f"{header}\n")
        out.write(f"{separator}\n")
        print_findings(findings, out)
    else:
        print(header)
        print(separator)
        print_findings(findings)
        print()
def run_full_audit(plan, parsed):
    return [
        ("VLAN & IP Audit", audit_vlan_ip(plan, parsed)),
        ("Routing Audit", audit_routing(plan, parsed)),
        ("DHCP & DNS Audit", audit_dhcp_dns(plan, parsed)),
        ("NAT / Internet Audit", audit_nat(plan, parsed)),
        ("Security Audit", audit_security(plan, parsed)),
    ]
def all_findings_from_sections(sections):
    findings = []
    for _, section_findings in sections:
        findings.extend(section_findings)
    return findings
def print_full_audit(sections):
    print("=" * 60)
    print("SMARTBRANCH 360 NETWORK AUDIT")
    print("=" * 60)
    print()
    for title, findings in sections:
        print_section(title, findings)
    all_findings = all_findings_from_sections(sections)
    score = compute_score(all_findings)
    print("=" * 60)
    print(f"NETWORK HEALTH SCORE: {score}/100")
    print("=" * 60)
    print()
    problems = [
        finding
        for finding in all_findings
        if finding.status in (FAIL, WARNING)
    ]
    if problems:
        print("ISSUES REQUIRING ATTENTION")
        print("-" * 50)
        print_findings(problems)
    else:
        print(
            "No FAIL or WARNING findings - "
            "network looks healthy based on the supplied output."
        )
    print()
    counts = {}
    for finding in all_findings:
        counts[finding.status] = (
            counts.get(finding.status, 0) + 1
        )
    summary = ", ".join(
        f"{status}: {counts.get(status, 0)}"
        for status in (
            PASS,
            WARNING,
            FAIL,
            NOT_VERIFIABLE,
        )
    )
    print(f"Summary -> {summary}")
def generate_report(
    plan,
    parsed,
    plan_path,
    show_path,
    report_path,
):
    sections = run_full_audit(plan, parsed)
    all_findings = all_findings_from_sections(sections)
    score = compute_score(all_findings)
    report_directory = os.path.dirname(report_path)
    if report_directory:
        os.makedirs(report_directory, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as out:
        out.write("=" * 60 + "\n")
        out.write("SMARTBRANCH 360 - NETWORK VALIDATION REPORT\n")
        out.write("=" * 60 + "\n")
        out.write(
            f"Generated: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        out.write(f"Plan file: {plan_path}\n")
        out.write(f"Show-output file: {show_path}\n\n")
        site = plan.get("site", {})
        out.write(
            f"Site: {site.get('name', 'Unknown')}\n\n"
        )
        for title, findings in sections:
            out.write(title.upper() + "\n")
            out.write("-" * 50 + "\n")
            print_findings(findings, out)
            out.write("\n")
        out.write("=" * 60 + "\n")
        out.write(
            f"NETWORK HEALTH SCORE: {score}/100\n"
        )
        out.write("=" * 60 + "\n\n")
        problems = [
            finding
            for finding in all_findings
            if finding.status in (FAIL, WARNING)
        ]
        if problems:
            out.write("ISSUES REQUIRING ATTENTION\n")
            out.write("-" * 50 + "\n")
            print_findings(problems, out)
        else:
            out.write(
                "No FAIL or WARNING findings - "
                "network looks healthy based on the supplied output.\n"
            )
        counts = {}
        for finding in all_findings:
            counts[finding.status] = (
                counts.get(finding.status, 0) + 1
            )
        summary = ", ".join(
            f"{status}: {counts.get(status, 0)}"
            for status in (
                PASS,
                WARNING,
                FAIL,
                NOT_VERIFIABLE,
            )
        )
        out.write(f"\nSummary -> {summary}\n")
    return report_path, score
BANNER = """
==================================================
          SMARTBRANCH 360
      NETWORK ASSURANCE TOOL
==================================================
"""
MENU = """
1. Validate Network Plan
2. Analyze Cisco Show Outputs
3. VLAN & IP Audit
4. DHCP & DNS Audit
5. Routing Audit
6. NAT / Internet Audit
7. Security Audit
8. Diagnose Faults
9. Run Full Audit
10. Generate Validation Report
0. Exit
"""
class Session:
    def __init__(self):
        self.plan = None
        self.plan_path = None
        self.parsed = None
        self.show_path = None
    def ensure_plan(self):
        if self.plan is None:
            print(
                f"No plan loaded. Loading default: "
                f"{DEFAULT_PLAN_FILE}"
            )
            self.load_plan(DEFAULT_PLAN_FILE)
        return self.plan is not None
    def ensure_show(self):
        if self.parsed is None:
            default_file = os.path.join(
                DEFAULT_SHOW_DIR,
                "working.txt",
            )
            print(
                f"No show output loaded. Loading default: "
                f"{default_file}"
            )
            self.load_show(default_file)
        return self.parsed is not None
    def load_plan(self, path):
        plan, error = load_plan(path)
        if error:
            print(f"ERROR: {error}")
            return False
        self.plan = plan
        self.plan_path = path
        site_name = plan.get(
            "site",
            {},
        ).get(
            "name",
            "(unnamed site)",
        )
        print(f"Loaded network plan: {site_name}")
        return True
    def load_show(self, path):
        parsed, error = load_show_outputs(path)
        if error and parsed is None:
            print(f"ERROR: {error}")
            return False
        if error:
            print(f"NOTE: {error}")
        self.parsed = parsed
        self.show_path = path
        device_count = len(parsed) if parsed else 0
        print(
            f"Loaded show output from {device_count} "
            f"device(s) in {path}"
        )
        return True
def prompt_path(message, default):
    entered = input(
        f"{message} [{default}]: "
    ).strip()
    return entered or default
def menu_load_plan(session):
    path = prompt_path(
        "Path to plan file",
        DEFAULT_PLAN_FILE,
    )
    session.load_plan(path)
def menu_load_show(session):
    print(
        "Sample files: working.txt, "
        "fault01_wrong_gateway.txt, "
        "fault02_missing_vlan.txt, "
        "fault03_bad_dhcp.txt, "
        "fault04_dns_acl.txt, "
        "fault05_nat.txt"
    )
    default_file = os.path.join(
        DEFAULT_SHOW_DIR,
        "working.txt",
    )
    path = prompt_path(
        "Path to show-output file",
        default_file,
    )
    session.load_show(path)
def menu_single_audit(session, audit_func, title):
    if not session.ensure_plan():
        return
    if not session.ensure_show():
        return
    findings = audit_func(
        session.plan,
        session.parsed,
    )
    print_section(
        title,
        findings,
    )
    score = compute_score(findings)
    print(
        f"Section score: {score}/100\n"
    )
def menu_diagnose_faults(session):
    if not session.ensure_plan():
        return
    if not session.ensure_show():
        return
    sections = run_full_audit(
        session.plan,
        session.parsed,
    )
    findings = all_findings_from_sections(
        sections
    )
    problems = [
        finding
        for finding in findings
        if finding.status
        in (
            FAIL,
            WARNING,
            NOT_VERIFIABLE,
        )
        and finding.has_diagnostics()
    ]
    print("=" * 60)
    print("FAULT DIAGNOSIS")
    print("=" * 60)
    if not problems:
        print(
            "No diagnosable issues found."
        )
        return
    print_findings(problems)
def menu_full_audit(session):
    if not session.ensure_plan():
        return
    if not session.ensure_show():
        return
    sections = run_full_audit(
        session.plan,
        session.parsed,
    )
    print_full_audit(sections)
def menu_generate_report(session):
    if not session.ensure_plan():
        return
    if not session.ensure_show():
        return
    report_path = prompt_path(
        "Report output path",
        DEFAULT_REPORT_FILE,
    )
    path, score = generate_report(
        session.plan,
        session.parsed,
        session.plan_path,
        session.show_path,
        report_path,
    )
    print(f"Report written to: {path}")
    print(
        f"Overall Network Health Score: {score}/100"
    )
def main():
    session = Session()
    print(BANNER)
    while True:
        print(MENU)
        choice = input(
            "Select an option: "
        ).strip()
        try:
            if choice == "1":
                menu_load_plan(session)
            elif choice == "2":
                menu_load_show(session)
            elif choice == "3":
                menu_single_audit(
                    session,
                    audit_vlan_ip,
                    "VLAN & IP Audit",
                )
            elif choice == "4":
                menu_single_audit(
                    session,
                    audit_dhcp_dns,
                    "DHCP & DNS Audit",
                )
            elif choice == "5":
                menu_single_audit(
                    session,
                    audit_routing,
                    "Routing Audit",
                )
            elif choice == "6":
                menu_single_audit(
                    session,
                    audit_nat,
                    "NAT / Internet Audit",
                )
            elif choice == "7":
                menu_single_audit(
                    session,
                    audit_security,
                    "Security Audit",
                )
            elif choice == "8":
                menu_diagnose_faults(session)
            elif choice == "9":
                menu_full_audit(session)
            elif choice == "10":
                menu_generate_report(session)
            elif choice == "0":
                print(
                    "Exiting SmartBranch 360 "
                    "Network Assurance Tool. Goodbye!"
                )
                break
            else:
                print(
                    "Invalid option. Choose a number from the menu."
                )
        except Exception as exc:
            print(
                f"Unexpected error while processing that option: "
                f"{exc}"
            )
        print()
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in (
        "-h",
        "--help",
    ):
        print(__doc__ or "SmartBranch 360 Network Assurance Tool")
    else:
        main()