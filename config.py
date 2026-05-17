from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
MEMOS_DIR = DATA_DIR / "memos"
LOGS_DIR = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "prompts"
DB_PATH = DATA_DIR / "intelligence.db"

MODEL_CLASSIFY = "claude-haiku-4-5-20251001"
MODEL_SCORE = "claude-sonnet-4-6"
MODEL_MEMO = "claude-sonnet-4-6"
PERPLEXITY_MODEL = "sonar-pro"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
ARXIV_BASE_URL = "https://export.arxiv.org/api/query"

LAYERS = ["gpu", "hbm", "networking", "dc_shell", "power", "cooling", "fab"]

LAYER_LABELS = {
    "gpu": "GPU / Accelerators",
    "hbm": "HBM Memory",
    "networking": "Rack Networking",
    "dc_shell": "Data-Center Shell",
    "power": "Power / Grid",
    "cooling": "Cooling",
    "fab": "Fab Capacity",
}

LAYER_RUBRICS = {
    "gpu": (
        "1=Abundant: lead times <4 weeks, no rationing, hyperscalers easily sourcing H100/H200/B200. "
        "2=Normal: lead times 4-12 weeks, standard allocation. "
        "3=Tight: lead times 12-26 weeks, hyperscalers prioritized over startups. "
        "4=Severely constrained: lead times >26 weeks, public allocation cuts reported. "
        "5=Acute bottleneck: lead times 1yr+, capex plans publicly revised due to GPU supply."
    ),
    "hbm": (
        "1=Abundant: SK Hynix/Samsung/Micron ahead of demand, pricing stable. "
        "2=Normal ramp: supply meeting demand at expected ramp pace. "
        "3=Allocation constraints: HBM3E allocation tiered, spot premiums emerging. "
        "4=Binding bottleneck: HBM explicitly cited as GPU shipment limiter by Nvidia/AMD. "
        "5=Severe shortage: HBM shortage halting accelerator builds, hyperscaler delays attributed to HBM."
    ),
    "networking": (
        "1=Commodity: 400G/800G optics and InfiniBand/Ethernet available, normal lead times. "
        "2=Normal: slight lead time extension but no project delays. "
        "3=Tight: NVLink switch or InfiniBand allocation constraints visible in hyperscaler commentary. "
        "4=Rack-scale constraint: networking delays cluster builds, companies publicly discussing workarounds. "
        "5=Critical bottleneck: networking cited as blocking AI cluster delivery."
    ),
    "dc_shell": (
        "1=Easy: permits <12 months, greenfield sites readily available. "
        "2=Normal: 12-18 month permitting, standard NIMBY friction. "
        "3=Siting constraints: moratoriums emerging in key markets (Virginia, Ireland, Singapore). "
        "4=Major constraints: hyperscalers publicly delaying MW announcements due to permitting. "
        "5=Crisis: hyperscalers explicitly blaming siting/permitting for capacity shortfalls."
    ),
    "power": (
        "1=Available: grid connection <2 year queue, utility power available at market rates. "
        "2=Normal queue: 2-3 year interconnection queue, manageable. "
        "3=Queue delays: >3 year queues in key ISO/RTO regions, hyperscalers seeking dedicated generation. "
        "4=Severe: >4 year queues, dedicated gas/nuclear/renewable required for new campuses. "
        "5=Crisis: projects cancelled or relocated specifically due to power unavailability."
    ),
    "cooling": (
        "1=Solved: air cooling sufficient for current rack densities. "
        "2=Manageable: liquid cooling available and being deployed at normal pace. "
        "3=Required: liquid cooling mandatory for GPU rack densities >50kW/rack. "
        "4=Constraint: thermal density limits visible in hyperscaler build specs and vendor commentary. "
        "5=Blocking: cooling constraints explicitly limiting AI cluster designs or deployments."
    ),
    "fab": (
        "1=Flexible: TSMC/Samsung/Intel capacity available, <6 month lead times on advanced nodes. "
        "2=Normal: 6-12 month lead times, standard capacity allocation. "
        "3=Tight: 2-3nm fully allocated, Nvidia/AMD/custom ASIC competing for same wafers. "
        "4=Scarce: TSMC CoWoS/SoIC packaging or leading-edge node explicitly rationed. "
        "5=Geopolitical disruption: export controls, Taiwan risk, or sanctions creating binding constraint."
    ),
}

INDUSTRIES = [
    "software_eng", "legal", "accounting", "insurance",
    "healthcare_admin", "finance_ops", "marketing",
    "customer_support", "manufacturing", "defense_aero",
]

INDUSTRY_LABELS = {
    "software_eng": "Software Engineering",
    "legal": "Legal",
    "accounting": "Accounting",
    "insurance": "Insurance",
    "healthcare_admin": "Healthcare Admin",
    "finance_ops": "Finance Ops",
    "marketing": "Marketing",
    "customer_support": "Customer Support",
    "manufacturing": "Manufacturing",
    "defense_aero": "Defense / Aerospace",
}

FACTORS = [
    "labor_cost", "workflow_repetitiveness", "digital_artifact",
    "error_cost", "regulatory_burden", "verification_feasibility", "tool_api_access",
]

FACTOR_LABELS = {
    "labor_cost": "Labor Cost",
    "workflow_repetitiveness": "Workflow Repetitiveness",
    "digital_artifact": "Digital Artifact Availability",
    "error_cost": "Error Cost",
    "regulatory_burden": "Regulatory Burden",
    "verification_feasibility": "Verification Feasibility",
    "tool_api_access": "Tool / API Access",
}

SIGNAL_QUERIES: dict[str, list[str]] = {
    # --- Track 1: Infrastructure bottleneck ---
    "gpu_lead_time": [
        "H200 B200 GPU lead time allocation hyperscaler {YYYY}",
        "Nvidia GPU supply constraint AI data center {YYYY}",
        "AMD MI350 MI300 availability cloud {YYYY}",
    ],
    "gpu_capex": [
        "Amazon AWS Microsoft Azure Google Meta AI capex spending {YYYY}",
        "hyperscaler capital expenditure AI infrastructure quarterly {YYYY}",
    ],
    "hbm_supply": [
        "SK Hynix HBM3E HBM4 supply capacity ramp {YYYY}",
        "Samsung Micron HBM memory AI GPU shortage {YYYY}",
        "high bandwidth memory bottleneck Nvidia {YYYY}",
    ],
    "networking": [
        "NVLink InfiniBand 800G optics AI cluster networking lead time {YYYY}",
        "rack scale networking constraint hyperscaler {YYYY}",
    ],
    "dc_shell_permit": [
        "data center permitting delay moratorium {YYYY}",
        "hyperscaler data center MW announcement permit {YYYY}",
        "data center REIT filing construction {YYYY}",
    ],
    "dc_shell_siting": [
        "data center siting Virginia Texas Ohio transmission constraint {YYYY}",
        "data center moratorium community opposition {YYYY}",
    ],
    "power_ppa": [
        "hyperscaler power purchase agreement nuclear renewable {YYYY}",
        "Microsoft Amazon Google energy deal data center {YYYY}",
    ],
    "power_queue": [
        "interconnection queue ISO RTO MISO PJM data center {YYYY}",
        "grid interconnection delay AI data center electricity {YYYY}",
    ],
    "power_gen": [
        "GE Vernova Siemens Energy gas turbine backlog order {YYYY}",
        "Eaton transformer lead time data center {YYYY}",
        "nuclear restart geothermal data center power {YYYY}",
    ],
    "cooling": [
        "liquid cooling direct-to-chip AI data center deployment {YYYY}",
        "PUE data center thermal density GPU rack cooling {YYYY}",
        "Vertiv cooling data center AI cluster {YYYY}",
    ],
    "fab": [
        "TSMC Arizona ramp 2nm 3nm CoWoS capacity {YYYY}",
        "Intel 18A Samsung foundry volume production {YYYY}",
        "CHIPS Act milestone semiconductor fab announcement {YYYY}",
    ],
    "fab_geo": [
        "BIS export control China AI chips restriction {YYYY}",
        "US Commerce semiconductor China retaliation Nvidia {YYYY}",
        "ASML EUV export control China restriction {YYYY}",
    ],
    # --- Track 2: Cross-cutting agent signals ---
    "agent_cli_adoption": [
        "Claude Code Codex CLI enterprise developer adoption {YYYY}",
        "AI coding agent enterprise deployment usage statistics {YYYY}",
    ],
    "agent_observability": [
        "AI agent observability tracing audit trail tool {YYYY}",
        "LLM agent monitoring enterprise platform {YYYY}",
    ],
    "hitl": [
        "human in the loop AI agent enterprise approval workflow {YYYY}",
        "agentic AI verification human review production {YYYY}",
    ],
    "agent_privacy": [
        "enterprise private on-premise LLM AI agent deployment {YYYY}",
        "VPC private cloud AI agent data sovereignty {YYYY}",
    ],
    "agent_benchmarks": [
        "AI agent tool use benchmark SWE-bench leaderboard {YYYY}",
        "agentic AI reliability production deployment benchmark {YYYY}",
    ],
    "agent_security": [
        "AI agent security incident prompt injection production {YYYY}",
        "agentic AI vulnerability enterprise attack {YYYY}",
    ],
    "vertical_agents": [
        "vertical AI agent startup funding series A {YYYY}",
        "legal accounting insurance AI agent company launch {YYYY}",
    ],
    # --- Track 2: Per-industry ---
    "industry_software_eng": [
        "AI coding agent enterprise software engineering deployment ROI {YYYY}",
        "Claude Code Cursor GitHub Copilot enterprise adoption {YYYY}",
    ],
    "industry_legal": [
        "legal AI agent law firm deployment Harvey Clio {YYYY}",
        "AI contract review discovery legal automation {YYYY}",
    ],
    "industry_accounting": [
        "accounting AI agent bookkeeping audit automation {YYYY}",
        "AI tax preparation reconciliation enterprise {YYYY}",
    ],
    "industry_insurance": [
        "insurance AI agent claims underwriting automation {YYYY}",
        "AI prior authorization insurance workflow {YYYY}",
    ],
    "industry_healthcare_admin": [
        "healthcare admin AI agent prior authorization scheduling {YYYY}",
        "medical billing coding AI automation hospital {YYYY}",
    ],
    "industry_finance_ops": [
        "finance operations AI agent FP&A reconciliation {YYYY}",
        "AI CFO financial reporting automation enterprise {YYYY}",
    ],
    "industry_marketing": [
        "marketing AI agent campaign creative automation enterprise {YYYY}",
        "AI ad generation segmentation marketing ops {YYYY}",
    ],
    "industry_customer_support": [
        "customer support AI agent call deflection deployment {YYYY}",
        "Sierra Decagon AI customer service enterprise {YYYY}",
    ],
    "industry_manufacturing": [
        "manufacturing AI agent industrial copilot deployment {YYYY}",
        "AI process automation factory enterprise {YYYY}",
    ],
    "industry_defense_aero": [
        "defense AI agent Palantir AIP DoD deployment {YYYY}",
        "aerospace AI automation military enterprise {YYYY}",
    ],
}

LAYER_TO_SIGNAL_TYPES: dict[str, list[str]] = {
    "gpu": ["gpu_lead_time", "gpu_capex"],
    "hbm": ["hbm_supply"],
    "networking": ["networking"],
    "dc_shell": ["dc_shell_permit", "dc_shell_siting"],
    "power": ["power_ppa", "power_queue", "power_gen"],
    "cooling": ["cooling"],
    "fab": ["fab", "fab_geo"],
}

CROSS_AGENT_SIGNAL_TYPES = [
    "agent_cli_adoption", "agent_observability", "hitl",
    "agent_privacy", "agent_benchmarks", "agent_security", "vertical_agents",
]

INDUSTRY_TO_SIGNAL_TYPES: dict[str, list[str]] = {
    industry: CROSS_AGENT_SIGNAL_TYPES + [f"industry_{industry}"]
    for industry in INDUSTRIES
}

ARXIV_QUERIES = [
    "agentic AI enterprise deployment verification",
    "LLM agent safety evaluation benchmark",
    "multi-agent workflow orchestration production",
    "AI agent tool use reliability",
]
