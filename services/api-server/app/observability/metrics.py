from prometheus_client import Counter, Gauge, Histogram

agent_tasks_total = Counter("agent_tasks_total", "Tasks created.")
agent_tasks_running = Gauge("agent_tasks_running", "Tasks currently running.")
agent_tasks_failed_total = Counter("agent_tasks_failed_total", "Tasks failed.")
agent_task_duration_seconds = Histogram("agent_task_duration_seconds", "Task duration.")
agent_task_resume_total = Counter("agent_task_resume_total", "Task resume operations.")

agent_subagents_running = Gauge("agent_subagents_running", "Subagents currently running.")
agent_subagents_queued = Gauge("agent_subagents_queued", "Subagents queued.")
agent_subagents_failed_total = Counter("agent_subagents_failed_total", "Subagents failed.")
agent_subagent_duration_seconds = Histogram("agent_subagent_duration_seconds", "Subagent duration.")
agent_subagent_recovery_total = Counter(
    "agent_subagent_recovery_total",
    "Subagent recovery actions.",
    ["action"],
)
agent_subagent_recovery_sweeps_total = Counter(
    "agent_subagent_recovery_sweeps_total",
    "Subagent recovery sweeps.",
)
agent_subagent_recovery_last_recovered = Gauge(
    "agent_subagent_recovery_last_recovered",
    "Subagents recovered by the last recovery sweep.",
)

sandbox_containers_total = Counter("sandbox_containers_total", "Sandbox containers allocated.")
sandbox_containers_running = Gauge("sandbox_containers_running", "Sandbox containers running.")
sandbox_start_duration_seconds = Histogram(
    "sandbox_start_duration_seconds",
    "Sandbox start duration.",
)
sandbox_command_duration_seconds = Histogram(
    "sandbox_command_duration_seconds",
    "Sandbox command duration.",
)
sandbox_command_timeout_total = Counter(
    "sandbox_command_timeout_total",
    "Sandbox command timeouts.",
)

warm_pool_idle_containers = Gauge("warm_pool_idle_containers", "WarmPool idle containers.")
warm_pool_busy_containers = Gauge("warm_pool_busy_containers", "WarmPool busy containers.")
warm_pool_hit_total = Counter("warm_pool_hit_total", "WarmPool hits.")
warm_pool_miss_total = Counter("warm_pool_miss_total", "WarmPool misses.")
warm_pool_acquire_duration_seconds = Histogram(
    "warm_pool_acquire_duration_seconds",
    "WarmPool acquire duration.",
)

model_calls_total = Counter("model_calls_total", "Model calls.")
model_call_duration_seconds = Histogram("model_call_duration_seconds", "Model call duration.")
model_call_errors_total = Counter("model_call_errors_total", "Model call errors.")
model_tokens_input_total = Counter("model_tokens_input_total", "Input tokens.")
model_tokens_output_total = Counter("model_tokens_output_total", "Output tokens.")
