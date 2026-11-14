"""Exercise signed session setup, cover binding, fixed size, and replay checks."""

import os
import tempfile

import numpy as np
import pandas as pd
from PIL import Image
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from fham.channel import AuxiliaryChannel, SQLiteReplayGuard
from fham.config import DATASET_DIR, RESULTS_DIR
from fham.experiments import _message
from fham.methods import BoundedAssignmentMethod


def main():
    state_file = tempfile.NamedTemporaryFile(prefix="fham-replay-", suffix=".sqlite", delete=False)
    state_path = state_file.name
    state_file.close()
    sender_identity = Ed25519PrivateKey.generate()
    receiver_identity = Ed25519PrivateKey.generate()
    sender_id = sender_identity.public_key().public_bytes_raw()
    receiver_id = receiver_identity.public_key().public_bytes_raw()
    rows = []

    for path in sorted((DATASET_DIR / "controlled").glob("*.png")):
        image = np.asarray(Image.open(path).convert("L"))
        method = BoundedAssignmentMethod(2)
        method.build_lookup_table(image)
        session_id = os.urandom(16)
        sender_ephemeral = X25519PrivateKey.generate()
        receiver_ephemeral = X25519PrivateKey.generate()
        sender_offer, sender_signature = AuxiliaryChannel.sign_ephemeral(
            sender_identity, sender_ephemeral, receiver_id, session_id
        )
        receiver_offer, receiver_signature = AuxiliaryChannel.sign_ephemeral(
            receiver_identity, receiver_ephemeral, sender_id, session_id
        )
        AuxiliaryChannel.verify_ephemeral(
            sender_id, receiver_id, sender_offer, sender_signature, session_id
        )
        AuxiliaryChannel.verify_ephemeral(
            receiver_id, sender_id, receiver_offer, receiver_signature, session_id
        )
        sender_key = AuxiliaryChannel.derive_session_key(
            sender_ephemeral, receiver_offer, session_id
        )
        receiver_key = AuxiliaryChannel.derive_session_key(
            receiver_ephemeral, sender_offer, session_id
        )
        assert sender_key == receiver_key
        guard = SQLiteReplayGuard(state_path)
        guard.register_session(session_id)
        for trial in range(5):
            message = _message(40, path.stem, trial)
            assignment = method.embed(message, image)
            if assignment is None:
                rows.append({"image": path.stem, "trial": trial, "feasible": 0})
                continue

            envelope = AuxiliaryChannel.protect_session(
                assignment, sender_key, image, session_id, trial, record_capacity=40
            )
            recovered_assignment = AuxiliaryChannel.recover_session(
                envelope, receiver_key, image, guard
            )
            recovered_message = method.extract(recovered_assignment, image)

            wrong_cover = image.copy()
            wrong_cover[0, 0] ^= 1
            try:
                AuxiliaryChannel.recover_session(
                    envelope, receiver_key, wrong_cover,
                    SQLiteReplayGuard(state_path)
                )
                cover_binding_rejected = 0
            except InvalidTag:
                cover_binding_rejected = 1

            try:
                restarted_guard = SQLiteReplayGuard(state_path)
                AuxiliaryChannel.recover_session(
                    envelope, receiver_key, image, restarted_guard
                )
                replay_rejected = 0
            except ValueError:
                replay_rejected = 1

            altered_offer = bytearray(sender_offer)
            altered_offer[0] ^= 1
            try:
                AuxiliaryChannel.verify_ephemeral(
                    sender_id, receiver_id, bytes(altered_offer), sender_signature,
                    session_id,
                )
                altered_offer_rejected = 0
            except ValueError:
                altered_offer_rejected = 1

            rows.append({
                "image": path.stem,
                "trial": trial,
                "session_id": session_id.hex(),
                "feasible": 1,
                "session_key_agreement": int(sender_key == receiver_key),
                "message_exact_recovery": int(recovered_message == message),
                "cover_substitution_rejected": cover_binding_rejected,
                "replay_rejected": replay_rejected,
                "altered_key_offer_rejected": altered_offer_rejected,
                "envelope_bytes": len(envelope),
            })

    raw = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_csv(RESULTS_DIR / "secure_channel_pilot_raw.csv", index=False)
    measured = raw.loc[raw["feasible"] == 1]
    handshake_bytes_per_session = 16 + 2 * (32 + 64)
    sessions = measured["session_id"].nunique()
    records_per_session = len(measured) / sessions
    fixed_record_bytes = int(measured["envelope_bytes"].iloc[0])
    summary = pd.DataFrame([{
        "trials": len(measured),
        "assignment_feasible": len(measured) / len(raw),
        "session_key_agreement": measured["session_key_agreement"].mean(),
        "exact_recovery": measured["message_exact_recovery"].mean(),
        "cover_substitution_rejected": measured["cover_substitution_rejected"].mean(),
        "replay_rejected": measured["replay_rejected"].mean(),
        "altered_key_offer_rejected": measured["altered_key_offer_rejected"].mean(),
        "envelope_bytes_min": measured["envelope_bytes"].min(),
        "envelope_bytes_max": measured["envelope_bytes"].max(),
        "sessions": sessions,
        "handshake_bytes_per_session": handshake_bytes_per_session,
        "records_per_session": records_per_session,
        "amortized_protocol_bytes_per_message": (
            fixed_record_bytes + handshake_bytes_per_session / records_per_session
        ),
    }])
    summary.to_csv(RESULTS_DIR / "secure_channel_pilot.csv", index=False)
    os.unlink(state_path)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
