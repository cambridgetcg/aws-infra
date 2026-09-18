# Historical Captioneer policy documents

These unchanged JSON files preserve the September 2026 review and containment
history for Cambridge TCG account `034362054546`. The five Captioneer IAM roles
were retired on **18 September 2026**. These files are **not deployment or
role-recreation templates**. See the [cleanup record](../../../docs/CAPTIONEER_CLEANUP.md)
for the deletion outcome and verification limits.

| Document | Historical status |
| --- | --- |
| [captioneer-quarantine-permissions.json](captioneer-quarantine-permissions.json) | Applied 17 September as inline policy `AWSInfraCaptioneerQuarantine20260917`; removed during role retirement on 18 September. |
| [captioneer-quarantine-trust.json](captioneer-quarantine-trust.json) | Applied 17 September to block new assumptions; its target roles were deleted on 18 September. |
| [captioneer-staging-github-trust.json](captioneer-staging-github-trust.json) | Proposed staging/main trust repair, **never deployed** and **superseded by retirement**. |

## Quarantine applied on 17 September

The two quarantine documents were applied at approximately 21:18 UTC to exactly
`captioneer-staging-github-terraform` and `captioneer-staging-github-deploy`.
The permission policy unconditionally denied all actions/resources. The trust
document had a deny and no allow statements. Both documents passed AWS Access
Analyzer validation without findings; their live copies matched, and all 12
sampled principal-policy decisions were explicit denies. Those simulations did
not test old session credentials or establish absence of prior misuse.

## Trust repair proposed but never deployed

The proposed repair restricted GitHub assumption to
`repo:cambridgetcg/captioneer:environment:staging`, `aud=sts.amazonaws.com`, and
`ref=refs/heads/main`. It did not narrow the roles' permission attachments.
AWS Access Analyzer reported zero errors and zero warnings, plus one
`CONFIRM_AUDIENCE_CLAIM_TYPE` suggestion. The document uses plain `StringEquals`
for audience, with no set qualifier. No real GitHub-token workflow test was
performed. Validation did not establish deployment readiness.

The [17 September IAM review](../../../docs/IAM_REVIEW_2026-09-17.md) retains the
source references and environment-protection gaps observed then. Retirement
superseded that repair proposal. Do not use these files or the archived bootstrap
to restore the former roles; any future Captioneer deployment would need its
own requirements, source/state ownership and access design.
