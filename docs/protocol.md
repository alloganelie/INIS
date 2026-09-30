# Protocole de Communication Inter-Agents INIS (§5, §29)

## 1. Structure de l'Enveloppe Commune (§5.1)
Chaque message inter-agents transmis via AMQP ou MQTT encapsule le format suivant :
```json
{
  "protocol_version": "1.0",
  "message_id": "MSG_01H...",
  "correlation_id": "CORR_01H...",
  "causation_id": null,
  "timestamp": "2026-09-28T12:00:00Z",
  "sender": {
    "agent_id": "AGT_01H...",
    "agent_version": "2.0.0"
  },
  "recipient": {
    "agent_id": "inis"
  },
  "message_type": "INFORMATION_REQUEST",
  "payload": {}
}
```

## 2. Idempotence et Déduplication (§5.3)
Tout récepteur d'un message DOIT vérifier la présence préalable de `message_id`. La retransmission d'un même identifiant ne doit pas déclencher une double exécution.

