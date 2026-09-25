# UniCredit Production Runbook

## Non-negotiable prerequisites

1. NeoNoble must hold the applicable PSP authorisation for the service(s) being offered.
2. Required EEA passporting/registration must be effective for Italy.
3. Obtain an eIDAS QWAC from a QTSP listed in the EU Trusted List.
4. Keep the private key exclusively in an HSM/secret manager.
5. Register the organisation/admin in the UniCredit Developer Portal.
6. Execute the TPP onboarding API over mTLS using the real QWAC.
7. Confirm the Production organisation/roles in the Developer Portal.
8. Configure AIS/PIS applications and redirect URIs.
9. Execute sandbox/SCA tests required by UniCredit.
10. Promote only after Production access is confirmed by UniCredit.

## Onboarding endpoint

POST https://api.unicredit.eu/tpp/v1/authentications

Required:
- TLS client authentication with the QWAC
- Content-Type: application/json
- X-Request-ID: unique per request
- OnBoardingRequest JSON body
- Digest when Signature is present/required
- Signature and TPP-Signature-Certificate when mandated

## Security

Never put a QWAC private key in Git, frontend code, Docker images, logs, tickets, or chat.
Never replace the QWAC or regulatory status with a boolean to bypass the gate.

## Production switch

The application must remain fail-closed until UniCredit has accepted the onboarding request and Production credentials are installed.
