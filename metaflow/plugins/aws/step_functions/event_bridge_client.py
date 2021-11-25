import base64
import json
from hashlib import sha1

from metaflow.util import to_bytes, to_unicode


class EventBridgeClient(object):
    def __init__(self, name):
        from ..aws_client import get_aws_client

        self._client = get_aws_client("events")
        self._dependent_state_machine_arn = None
        self._cron = None
        self.name = format(name)

    def cron(self, cron):
        self._cron = cron
        return self

    def dependent_state_machine_arn(self, dep_state_machine_arn):
        self._dependent_state_machine_arn = dep_state_machine_arn
        return self

    def role_arn(self, role_arn):
        self.role_arn = role_arn
        return self

    def state_machine_arn(self, state_machine_arn):
        self.state_machine_arn = state_machine_arn
        return self

    def schedule(self):
        if not self._cron and not self._dependent_state_machine_arn:
            # reset the schedule
            self._disable()
        # If dependent state machine arn set, use that to create schedule
        elif self._dependent_state_machine_arn:
            self._set_dependent_flow()
        # If not, use cron
        else:
            self._set_cron()
        return self.name

    def _disable(self):
        try:
            self._client.disable_rule(Name=self.name)
        except self._client.exceptions.ResourceNotFoundException:
            pass

    def _create_event_pattern(self):

        trigger_definition = {
            "source": ["aws.states"],
            "detail-type": [
                "Step Functions Execution Status Change"
            ],
            "detail": {
                "status": ["SUCCEEDED"],
                "stateMachineArn": [
                    self._dependent_state_machine_arn
                ]
            }
        }

        return trigger_definition

    def _set_dependent_flow(self):
        # Generate a new rule or update existing rule.
        self._client.put_rule(
            Name=self.name,
            EventPattern=json.dumps(self._create_event_pattern()),
            Description="Metaflow generated rule for %s" % self.name,
            State="ENABLED",
        )
        # Assign AWS Step Functions ARN to the rule as a target.
        self._client.put_targets(
            Rule=self.name,
            Targets=[
                {
                    "Id": self.name,
                    "Arn": self.state_machine_arn,
                    # Set input parameters to empty.
                    "Input": json.dumps({"Parameters": json.dumps({})}),
                    "RoleArn": self.role_arn,
                }
            ],
        )

    def _set_cron(self):
        # Generate a new rule or update existing rule.
        self._client.put_rule(
            Name=self.name,
            ScheduleExpression="cron(%s)" % self._cron,
            Description="Metaflow generated rule for %s" % self.name,
            State="ENABLED",
        )
        # Assign AWS Step Functions ARN to the rule as a target.
        self._client.put_targets(
            Rule=self.name,
            Targets=[
                {
                    "Id": self.name,
                    "Arn": self.state_machine_arn,
                    # Set input parameters to empty.
                    "Input": json.dumps({"Parameters": json.dumps({})}),
                    "RoleArn": self.role_arn,
                }
            ],
        )


def format(name):
    # AWS Event Bridge has a limit of 64 chars for rule names.
    # We truncate the rule name if the computed name is greater
    # than 64 chars and append a hashed suffix to ensure uniqueness.
    if len(name) > 64:
        name_hash = to_unicode(base64.b32encode(sha1(to_bytes(name)).digest()))[
            :16
        ].lower()
        # construct an 64 character long rule name
        return "%s-%s" % (name[:47], name_hash)
    else:
        return name
