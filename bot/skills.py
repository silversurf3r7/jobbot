"""Skill taxonomy and extraction for DevOps/SRE/Platform job descriptions.

Each skill maps to (category, [regex patterns]). Patterns are case-insensitive
unless prefixed with "cs:" — used for tokens that collide with English words
(Go, Chef, Puppet, Flux, ...) or are acronyms (EKS, S3) that never appear
lowercase in earnest.
"""
import re

SKILLS = {
    # --- Infrastructure as Code ---
    "Terraform":       ("IaC", [r"terraform"]),
    "OpenTofu":        ("IaC", [r"opentofu|open tofu"]),
    "Pulumi":          ("IaC", [r"pulumi"]),
    "CloudFormation":  ("IaC", [r"cloud ?formation"]),
    "AWS CDK":         ("IaC", [r"aws cdk|cloud development kit|\bcdk\b"]),
    "Crossplane":      ("IaC", [r"crossplane"]),
    "Bicep":           ("IaC", [r"cs:\bBicep\b"]),
    "Terragrunt":      ("IaC", [r"terragrunt"]),

    # --- Config management / image building ---
    "Ansible":         ("Config Mgmt", [r"ansible"]),
    "Chef":            ("Config Mgmt", [r"cs:\bChef\b"]),
    "Puppet":          ("Config Mgmt", [r"cs:\bPuppet\b"]),
    "SaltStack":       ("Config Mgmt", [r"salt ?stack"]),
    "Packer":          ("Config Mgmt", [r"cs:\bPacker\b"]),

    # --- Containers & orchestration ---
    "Docker":          ("Containers", [r"\bdocker\b"]),
    "Kubernetes":      ("Containers", [r"kubernetes|\bk8s\b"]),
    "Helm":            ("Containers", [r"\bhelm\b"]),
    "Kustomize":       ("Containers", [r"kustomize"]),
    "Istio":           ("Containers", [r"istio"]),
    "Envoy":           ("Containers", [r"cs:\bEnvoy\b"]),
    "OpenShift":       ("Containers", [r"open ?shift"]),
    "Nomad":           ("Containers", [r"cs:\bNomad\b"]),
    "Karpenter":       ("Containers", [r"karpenter"]),
    "Rancher":         ("Containers", [r"cs:\bRancher\b"]),

    # --- Clouds ---
    "AWS":             ("Cloud", [r"\baws\b|amazon web services"]),
    "GCP":             ("Cloud", [r"\bgcp\b|google cloud"]),
    "Azure":           ("Cloud", [r"\bazure\b"]),
    "Oracle Cloud":    ("Cloud", [r"oracle cloud|\boci\b"]),
    "DigitalOcean":    ("Cloud", [r"digital ?ocean"]),
    "Cloudflare":      ("Cloud", [r"cloudflare"]),
    "Bare metal":      ("Cloud", [r"bare[- ]metal|on[- ]prem"]),

    # --- Cloud services (the EKS-vs-ECS kind of signal) ---
    "EKS":             ("Cloud Services", [r"cs:\bEKS\b"]),
    "ECS":             ("Cloud Services", [r"cs:\bECS\b"]),
    "Fargate":         ("Cloud Services", [r"fargate"]),
    "Lambda":          ("Cloud Services", [r"cs:\bLambdas?\b"]),
    "EC2":             ("Cloud Services", [r"cs:\bEC2\b"]),
    "S3":              ("Cloud Services", [r"cs:\bS3\b"]),
    "RDS":             ("Cloud Services", [r"cs:\bRDS\b"]),
    "DynamoDB":        ("Cloud Services", [r"dynamo ?db"]),
    "GKE":             ("Cloud Services", [r"cs:\bGKE\b"]),
    "AKS":             ("Cloud Services", [r"cs:\bAKS\b"]),
    "Cloud Run":       ("Cloud Services", [r"cloud run"]),

    # --- CI/CD ---
    "GitHub Actions":  ("CI/CD", [r"github actions?|\bgha\b"]),
    "GitLab CI":       ("CI/CD", [r"gitlab[- ]?ci|gitlab pipelines?"]),
    "GitLab":          ("CI/CD", [r"gitlab"]),
    "Jenkins":         ("CI/CD", [r"jenkins"]),
    "CircleCI":        ("CI/CD", [r"circle ?ci"]),
    "Buildkite":       ("CI/CD", [r"buildkite"]),
    "Azure DevOps":    ("CI/CD", [r"azure devops|\bado\b pipelines?"]),
    "TeamCity":        ("CI/CD", [r"team ?city"]),
    "Travis CI":       ("CI/CD", [r"travis[- ]?ci"]),
    "Spinnaker":       ("CI/CD", [r"spinnaker"]),
    "Tekton":          ("CI/CD", [r"tekton"]),
    "Bazel":           ("CI/CD", [r"cs:\bBazel\b"]),

    # --- GitOps ---
    "Argo CD":         ("GitOps", [r"argo ?cd"]),
    "Argo Workflows":  ("GitOps", [r"argo workflows?"]),
    "Flux":            ("GitOps", [r"cs:\bFluxCD\b|cs:\bFlux(?: ?CD|v?2)\b"]),
    "GitOps":          ("GitOps", [r"gitops"]),

    # --- Observability ---
    "Prometheus":      ("Observability", [r"prometheus"]),
    "Grafana":         ("Observability", [r"grafana"]),
    "Datadog":         ("Observability", [r"data ?dog"]),
    "New Relic":       ("Observability", [r"new ?relic"]),
    "Splunk":          ("Observability", [r"splunk"]),
    "Elasticsearch/ELK": ("Observability", [r"elastic ?search|\belk\b|logstash|kibana|opensearch"]),
    "OpenTelemetry":   ("Observability", [r"open ?telemetry|\botel\b"]),
    "Loki":            ("Observability", [r"cs:\bLoki\b"]),
    "Jaeger":          ("Observability", [r"jaeger"]),
    "CloudWatch":      ("Observability", [r"cloud ?watch"]),
    "PagerDuty":       ("Observability", [r"pager ?duty"]),
    "Sentry":          ("Observability", [r"cs:\bSentry\b"]),
    "Honeycomb":       ("Observability", [r"honeycomb"]),
    "Nagios":          ("Observability", [r"nagios"]),
    "Zabbix":          ("Observability", [r"zabbix"]),

    # --- Languages & scripting ---
    "Python":          ("Languages", [r"\bpython\b"]),
    "Go":              ("Languages", [r"golang|cs:\bGo\b(?![- ]?(?:to|Live|live|getter|Getters))"]),
    "Bash/Shell":      ("Languages", [r"\bbash\b|shell script"]),
    "PowerShell":      ("Languages", [r"power ?shell"]),
    "Ruby":            ("Languages", [r"\bruby\b"]),
    "Java":            ("Languages", [r"\bjava\b(?!script)"]),
    "JavaScript/Node": ("Languages", [r"javascript|typescript|node\.?js"]),
    "Rust":            ("Languages", [r"cs:\bRust\b"]),
    "Groovy":          ("Languages", [r"groovy"]),
    "C++":             ("Languages", [r"c\+\+"]),

    # --- Data stores & streaming ---
    "PostgreSQL":      ("Data", [r"postgres(?:ql)?"]),
    "MySQL":           ("Data", [r"mysql|mariadb"]),
    "Redis":           ("Data", [r"\bredis\b|valkey"]),
    "MongoDB":         ("Data", [r"mongo ?db"]),
    "Kafka":           ("Data", [r"kafka"]),
    "RabbitMQ":        ("Data", [r"rabbit ?mq"]),
    "Cassandra":       ("Data", [r"cassandra"]),
    "Snowflake":       ("Data", [r"cs:\bSnowflake\b"]),
    "Airflow":         ("Data", [r"airflow"]),
    "ClickHouse":      ("Data", [r"click ?house"]),

    # --- Security & secrets ---
    "Vault":           ("Security", [r"cs:\bVault\b", r"hashicorp vault"]),
    "Snyk":            ("Security", [r"snyk"]),
    "Trivy":           ("Security", [r"trivy"]),
    "SOC 2":           ("Security", [r"soc ?2"]),
    "FedRAMP":         ("Security", [r"fedramp"]),
    "IAM":             ("Security", [r"cs:\bIAM\b"]),
    "Zero Trust":      ("Security", [r"zero[- ]trust"]),
    "DevSecOps":       ("Security", [r"devsecops"]),

    # --- Networking & web serving ---
    "Nginx":           ("Networking", [r"nginx"]),
    "HAProxy":         ("Networking", [r"haproxy"]),
    "Kong":            ("Networking", [r"cs:\bKong\b"]),
    "Traefik":         ("Networking", [r"traefik"]),
    "Consul":          ("Networking", [r"cs:\bConsul\b"]),
    "DNS":             ("Networking", [r"cs:\bDNS\b"]),
    "VPC":             ("Networking", [r"cs:\bVPCs?\b"]),
    "Service mesh":    ("Networking", [r"service mesh"]),
    "Linux":           ("Networking", [r"linux|ubuntu|debian|centos|rhel|red hat enterprise"]),

    # --- Practices ---
    "SLOs/SLIs":       ("Practices", [r"\bslos?\b|\bslis?\b|service[- ]level objective"]),
    "Incident response": ("Practices", [r"incident (?:response|management|commander)"]),
    "On-call":         ("Practices", [r"on[- ]call"]),
    "Chaos engineering": ("Practices", [r"chaos (?:engineering|monkey|testing)"]),
    "Observability":   ("Practices", [r"observability"]),
    "FinOps":          ("Practices", [r"finops|cost optimi[sz]ation|cloud cost"]),
    "Platform engineering": ("Practices", [r"platform engineering|internal developer platform|\bidp\b"]),
    "Serverless":      ("Practices", [r"serverless"]),
    "Microservices":   ("Practices", [r"micro[- ]?services"]),
    "MLOps":           ("Practices", [r"mlops|\bml infra"]),
    "Backstage":       ("Practices", [r"cs:\bBackstage\b"]),
}

CATEGORIES = sorted({cat for cat, _ in SKILLS.values()})

# Head-to-head groups the dashboard renders as matchup cards.
MATCHUPS = [
    ("IaC: Terraform vs the field", ["Terraform", "Pulumi", "CloudFormation", "AWS CDK", "OpenTofu", "Crossplane"]),
    ("Managed Kubernetes & containers", ["EKS", "ECS", "GKE", "AKS", "Fargate", "OpenShift"]),
    ("CI/CD systems", ["GitHub Actions", "GitLab CI", "Jenkins", "CircleCI", "Azure DevOps", "Buildkite"]),
    ("GitOps delivery", ["Argo CD", "Flux", "Spinnaker", "Tekton"]),
    ("Monitoring & APM", ["Prometheus", "Grafana", "Datadog", "New Relic", "Splunk", "OpenTelemetry"]),
    ("Clouds", ["AWS", "GCP", "Azure", "Oracle Cloud", "Bare metal"]),
    ("Config management", ["Ansible", "Chef", "Puppet", "SaltStack"]),
    ("Scripting & languages", ["Python", "Go", "Bash/Shell", "PowerShell", "Rust"]),
    ("Log & search stacks", ["Elasticsearch/ELK", "Splunk", "Loki", "CloudWatch"]),
]


def _compile():
    compiled = []
    for name, (cat, patterns) in SKILLS.items():
        regs = []
        for p in patterns:
            # split alternatives so a "cs:" prefix applies per alternative
            for alt in re.split(r"\|(?=cs:)", p):
                if alt.startswith("cs:"):
                    regs.append(re.compile(alt[3:]))
                else:
                    regs.append(re.compile(alt, re.IGNORECASE))
        compiled.append((name, cat, regs))
    return compiled


_COMPILED = _compile()


def extract_skills(text):
    """Return the set of canonical skill names mentioned in text."""
    found = set()
    for name, _cat, regs in _COMPILED:
        for r in regs:
            if r.search(text):
                found.add(name)
                break
    return found


def category_of(skill):
    return SKILLS[skill][0]


if __name__ == "__main__":
    import sys
    sample = sys.stdin.read() if not sys.stdin.isatty() else (
        "We use Terraform and Pulumi on AWS (EKS, not ECS). CI runs on GitHub Actions "
        "and some legacy Jenkins. Observability via Prometheus/Grafana and Datadog. "
        "You write Go and Python, ship with Argo CD, and go to meetings.")
    print(sorted(extract_skills(sample)))
