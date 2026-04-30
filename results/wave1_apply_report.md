# Wave 1 Verified Decision Apply Report

Generated: 2026-04-21T21:19:10
Source CSV: `/Users/Start Up/Research Project /VSL26/results/final_drug_review_actions.csv`
Database backup: `/Users/Start Up/Research Project /VSL26/vaipe_drugs.db.backup_wave1`

## Summary

- Total verified rows processed: 32
- Aliases added: 25
- Aliases skipped already exists: 0
- Traditional entries added: 7
- Traditional entries skipped: 0
- Drop entries added: 0
- Drop entries skipped: 0
- Errors: 0

## Schema Changes

- drugs.name_generic rebuilt as nullable
- drugs.atc_code already nullable
- drugs.is_traditional added during rebuild

## Row Log

| drug_name_extracted | decision | status | detail |
|---|---|---|---|
| dixirein | alias | added | alias added -> atc_r05cb03_carbocisteine; target resolution: matched KB term in VERIFIED notes: 'carbocisteine' |
| sergurop | alias | added | alias added -> loratadine; target resolution: matched KB term in VERIFIED notes: 'Loratadine' |
| chorlatcyn | traditional | added | traditional entry added -> chorlatcyn |
| bloza | alias | added | alias added -> atc_c09ca01_losartan; target resolution: matched KB term in VERIFIED notes: 'losartan' |
| ingaron 200 dst | alias | added | alias added -> atc_j01dd13_cefpodoxime; target resolution: matched note synonym 'cefpodoxime proxetil' -> 'cefpodoxime' |
| mezafen | alias | added | alias added -> atc_m02aa31_loxoprofen; target resolution: matched note synonym 'loxoprofen sodium' -> 'loxoprofen' |
| c floode | alias | added | alias added -> atc_g01ad03_ascorbic_acid; target resolution: matched note synonym 'vitamin c' -> 'ascorbic acid' |
| alfachim | alias | added | alias added -> atc_b06aa04_chymotrypsin; target resolution: matched note synonym 'alphachymotrypsin' -> 'chymotrypsin' |
| fudcime | alias | added | alias added -> atc_j01dd08_cefixime; target resolution: matched KB term in VERIFIED notes: 'cefixime' |
| livonic | traditional | added | traditional entry added -> livonic |
| carudxan | alias | added | alias added -> atc_c02ca04_doxazosin; target resolution: matched note synonym 'doxazosin mesylate' -> 'doxazosin' |
| famogast | alias | added | alias added -> atc_a02ba03_famotidine; target resolution: matched KB term in VERIFIED notes: 'famotidine' |
| gluzitop | alias | added | alias added -> atc_a10bb09_gliclazide; target resolution: matched KB term in VERIFIED notes: 'gliclazide' |
| medibogan | traditional | added | traditional entry added -> medibogan |
| bố gan p h | traditional | added | traditional entry added -> bo_gan_p_h |
| kahagan | traditional | added | traditional entry added -> kahagan |
| milurit | alias | added | alias added -> atc_m04aa01_allopurinol; target resolution: matched KB term in VERIFIED notes: 'allopurinol' |
| nifedipin hasan 20 retard | alias | added | alias added -> atc_c08ca05_nifedipine; target resolution: matched KB term in VERIFIED notes: 'nifedipine' |
| nifedipin t stada retard | alias | added | alias added -> atc_c08ca05_nifedipine; target resolution: matched KB term in VERIFIED notes: 'nifedipine' |
| vitamin c stada | alias | added | alias added -> atc_g01ad03_ascorbic_acid; target resolution: matched note synonym 'vitamin c' -> 'ascorbic acid' |
| gaphyton s | traditional | added | traditional entry added -> gaphyton_s |
| goutcolcin | alias | added | alias added -> atc_m04ac01_colchicine; target resolution: matched KB term in VERIFIED notes: 'colchicine' |
| sadapron | alias | added | alias added -> atc_m04aa01_allopurinol; target resolution: matched KB term in VERIFIED notes: 'allopurinol' |
| becosemid | alias | added | alias added -> atc_c03ca01_furosemide; target resolution: matched KB term in VERIFIED notes: 'furosemide' |
| mediplex | alias | added | alias added -> atc_d06bb03_aciclovir; target resolution: matched note synonym 'acyclovir' -> 'aciclovir' |
| anpemux | alias | added | alias added -> atc_r05cb03_carbocisteine; target resolution: matched KB term in VERIFIED notes: 'carbocisteine' |
| dorocron | alias | added | alias added -> atc_a10bb09_gliclazide; target resolution: matched KB term in VERIFIED notes: 'gliclazide' |
| normagut | alias | added | alias added -> atc_a07fa02_saccharomyces_boulardii; target resolution: matched KB term in VERIFIED notes: 'saccharomyces boulardii' |
| spasvina | alias | added | alias added -> atc_a03ax08_alverine; target resolution: matched note synonym 'alverine citrate' -> 'alverine' |
| tioga | traditional | added | traditional entry added -> tioga |
| pyme diapromr | alias | added | alias added -> atc_a10bb09_gliclazide; target resolution: matched KB term in VERIFIED notes: 'gliclazide' |
| vitamincstada | alias | added | alias added -> atc_g01ad03_ascorbic_acid; target resolution: matched note synonym 'vitamin c' -> 'ascorbic acid' |

## Errors

- None
