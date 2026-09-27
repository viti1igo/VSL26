# Google Forms Builder for VSL Gloss Expert Survey

This folder contains reusable Apps Script builders for the expert gloss survey.
Generated survey images, response files, and private form links are not committed.

## Recommended Flow

1. Generate local survey assets with `python export_expert_survey.py`.
2. Upload `expert_survey/images/` to Google Drive as one folder.
3. Copy the Drive folder ID from the folder URL.
4. Open <https://script.google.com/> and create a new Apps Script project.
5. Paste `Code_no_csv_bilingual_folder_fixed.gs`.
6. Replace the folder ID constant if needed.
7. Run `createVslGlossSurvey()`.
8. Approve permissions and copy the edit/live URLs from Apps Script logs.

## Updating an Existing Form

Use `update_existing_form_bilingual.gs` only when the current Google account has
edit access to the target form.

If Apps Script reports that no item with the ID can be found:

- confirm the form ID is copied from the edit URL, not the public live URL
- confirm the script is running under the form owner/editor account
- use Drive search or a helper function to find editable forms

## Expert-Facing Form Contents

Each question contains:

- respondent code field at the start of the form
- one prescription image
- generated gloss
- required 1-5 score
- optional comment field

Do not show hidden mapping data, extraction debug data, or method labels to
experts unless the experiment explicitly requires an unblinded review.

## Private Data

Do not commit:

- active form edit links
- respondent data
- response spreadsheets
- private Drive folder URLs
- prescription images that are not approved for public distribution
