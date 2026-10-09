# Glazing Configuration

Room 1 is the room on the right when entering the facility.
Room 2 is the room on the left when entering the facility.

## Glazing Configuration in Room 1

skylight:

SK 1.1

3x3 panels:

| DR 1.3 | DR 1.6 | DR 1.9 |
| DR 1.2 | DR 1.5 | DR 1.8 |
| DR 1.1 | DR 1.4 | DR 1.7 |

## Glazing Configuration in Room 2

skylight:

SK 1.2

3x3 panels:

| DR 2.3 | DR 2.6 | DR 2.9 |
| DR 2.2 | DR 2.5 | DR 2.8 |
| DR 2.1 | DR 2.4 | DR 2.7 |

## Halio window IDs

Halio identifies each window by UUID. The service uses these IDs directly in
production (there is no local mapping file). The table comes from the
controller's window listing captured during bring-up
(`svc/tests/fixtures/halio/exampleWindowResp.json`).

The last column is the panel ID from the retired `svc/data/window_mapping.json`,
kept for reference. It does not match the simulator's panel IDs: the HMI
places simulated P01 to P09 in Room 1, while the old mapping put them in Room 2.

| Halio name | Room | Position | Halio window UUID | Old mapping ID |
| --- | --- | --- | --- | --- |
| DR-1.1 | 1 | bottom left | `2974220d-1f66-41d1-95b3-42346a74a515` | P16 |
| DR-1.2 | 1 | middle left | `a845e392-18c8-4864-8659-8a857825b0b7` | P13 |
| DR-1.3 | 1 | top left | `8bb7c072-4594-48f0-88be-ff0bf8214c90` | P10 |
| DR-1.4 | 1 | bottom center | `c849bebc-48da-4db9-9e10-861479cc6d28` | P17 |
| DR-1.5 | 1 | middle center | `7823b993-3e7b-412b-a722-0deb73b4c0f5` | P14 |
| DR-1.6 | 1 | top center | `9e04faf5-a7cb-4374-9664-1bb28fa22ce2` | P11 |
| DR-1.7 | 1 | bottom right | `40e77fda-1635-4eac-b1dd-433b3a376101` | P18 |
| DR-1.8 | 1 | middle right | `7bb07eab-d042-4d20-b893-81d277aca281` | P15 |
| DR-1.9 | 1 | top right | `e4adaf7a-c158-4823-9b2d-42859bc00952` | P12 |
| DR-2.1 | 2 | bottom left | `780c37dc-8de5-49a2-ada5-5e9883853d47` | P07 |
| DR-2.2 | 2 | middle left | `3f8c0b43-0a6b-4074-9d8b-bb8b4983bcc5` | P04 |
| DR-2.3 | 2 | top left | `9df3c14c-df11-4497-b510-baecbf032bcf` | P01 |
| DR-2.4 | 2 | bottom center | `eb6452de-49d7-4c0f-8879-42d45bd02435` | P08 |
| DR-2.5 | 2 | middle center | `f2b6ecfb-2afa-40ee-b6b6-6d1b1bd49ef2` | P05 |
| DR-2.6 | 2 | top center | `6073d723-8279-41a3-b6b1-cea79b13fc04` | P02 |
| DR-2.7 | 2 | bottom right | `4c19c221-b4b6-4f83-8718-6b1296c39299` | P09 |
| DR-2.8 | 2 | middle right | `c35707eb-c879-4e06-a22c-c8bf54c8dea9` | P06 |
| DR-2.9 | 2 | top right | `1082c0c5-eb3c-47f8-9da4-2e4677f3cc5a` | P03 |
| SK-1.1 | 1 | skylight | `076f6469-8612-41f8-9f98-7a0dc9530296` | SK1 |
| SK-1.2 | 2 | skylight | `7b545fab-8317-4eeb-afd4-037c1e866191` | SK2 |
