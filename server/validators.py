"""
LockIn Request Validators
CM2211 Group 07 — Internet of Things

Marshmallow schemas for validating inbound API requests.
"""

from marshmallow import Schema, fields, validate, ValidationError, post_load
from typing import Dict, Any


class DistractionSchema(Schema):
    """Schema for individual distraction event."""

    timestamp = fields.DateTime(required=True, format='iso')
    type = fields.Str(
        required=True,
        validate=validate.OneOf(['phone', 'posture']),
        error_messages={'validator_failed': 'type must be "phone" or "posture"'}
    )
    confidence = fields.Float(required=False, allow_none=True)

    class Meta:
        strict = True


class SessionIngestSchema(Schema):
    """Schema for session ingest request (Pi → Server, F6)."""

    timestamp = fields.DateTime(required=True, format='iso')
    duration_mins = fields.Float(
        required=True,
        validate=validate.Range(min=0.1, max=120),
        error_messages={'validator_failed': 'duration_mins must be between 0.1 and 120'}
    )
    distraction_count = fields.Integer(
        required=True,
        validate=validate.Range(min=0),
        error_messages={'validator_failed': 'distraction_count must be >= 0'}
    )
    focus_score = fields.Float(
        required=True,
        validate=validate.Range(min=0, max=100),
        error_messages={'validator_failed': 'focus_score must be between 0 and 100'}
    )
    streak_days = fields.Integer(
        required=True,
        validate=validate.Range(min=0),
        error_messages={'validator_failed': 'streak_days must be >= 0'}
    )
    distractions = fields.List(
        fields.Nested(DistractionSchema),
        required=False,
        load_default=[]
    )

    class Meta:
        strict = True

    @post_load
    def convert_timestamps(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Convert datetime objects to ISO 8601 strings for storage."""
        if 'timestamp' in data:
            data['timestamp'] = data['timestamp'].isoformat()
        if 'distractions' in data:
            for distraction in data['distractions']:
                if 'timestamp' in distraction and hasattr(distraction['timestamp'], 'isoformat'):
                    distraction['timestamp'] = distraction['timestamp'].isoformat()
        return data


class LoginSchema(Schema):
    """Schema for login form."""

    username = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=80),
        error_messages={'validator_failed': 'username is required'}
    )
    password = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        error_messages={'validator_failed': 'password is required'}
    )

    class Meta:
        strict = True


def validate_json_request(schema: Schema, data: Any) -> tuple[Dict | None, Dict | None]:
    """
    Validate request data against a schema.

    Args:
        schema: Marshmallow schema instance
        data: Data to validate

    Returns:
        tuple: (validated_data, error_dict) — one will be None
    """
    try:
        validated = schema.load(data)
        return validated, None
    except ValidationError as err:
        return None, err.messages
