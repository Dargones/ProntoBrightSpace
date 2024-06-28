# Pronto BrightSpace Integration

This repository contains scripts that allow:
- `[brightspace_download.py]` downloading latest user and enrollment data from BrightSpace
- `[sync_with_pronto.py]` creating input tables for the Pronto messaging app that create a group for every BrightSpace app and enrolls relevant users to each group.

## Requirements

- python3 with the latest version of the `requests` package
- client id, client secret, and a refresh token for Brightspace API.

## How to use

1. Update `config.json` with the refresh token, client secret, and client id of your Brightspace application (read https://community.d2l.com/brightspace/kb/articles/1196-how-to-obtain-an-oauth-2-0-refresh-token on how to do this)
2. Run `python3 brightspace_download.py` to download latest user and enrollment data from DataHub. The script will create a timestamped folder with new data.
3. Run `python3 sync_with_pronto.py [BRIGHTSPACE_DATA_DIR] [ORG_UNIT_NAME]`. The script will create a timestamped directory with input tables for the Pronto messaging app. For `BRIGHTSPACE_DATA_DIR` use the name of the directory created in step 2, for `ORG_UNIT_NAME`, use the name(s), code(s), or id(s) of organisational units or courses that you wish to sync with Pronto.

## Notes

- The current set up can only add new users/groups/categories and will never delete existing ones.
- When downloading data from Brightspace, the script uses Differential datasets to get most up to date information about users and courses. Even so, these datasets are only updates once a day, so you may have to wait up to 24 hours after you make an update to BrightSpace for that update to propagate to Pronto.
- The code has been only minimally tested.
- This repository uses code originally published by BrightSpace under Apache 2.0 commercial use license (https://github.com/Brightspace/bds-headless-client-example/tree/master)