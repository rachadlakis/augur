"""The Training Agent: plan, estimate, launch and monitor a training run.

No GPU work happens in this package. It produces and validates a
``TrainingPlan``, hands it to a job manager, and reports durable job state.
"""

