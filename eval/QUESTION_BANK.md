# Question bank

All 77 reported questions, grouped two ways: by how hard the question is, and by the kind of
document it is asked about. The pass marks come from the last saved run of each set.
Written by `python eval/question_bank.py`; do not edit by hand.

## Results by difficulty level

| Level | Kind of question | What makes it hard | Questions | Passed |
| --- | --- | --- | --- | --- |
| 1 | One fact | The answer is one fact stated in one place | 30 | 24 / 25 |
| 2 | Several facts, one passage | A list or a few facts that sit together | 7 | 2 / 2 |
| 3 | Facts from different places | The answer needs two passages, or two documents | 12 | 9 / 9 |
| 4 | A near-miss sits close by | A similar but wrong value is in another document, version or section | 7 | 3 / 3 |
| 5 | Must be refused | The documents are on topic but do not state the fact, or it is off topic | 21 | 17 / 17 |
| | **All** | | 77 | 55 / 56 |

## Results by document format

| Format of the document that holds the answer | Questions | Passed |
| --- | --- | --- |
| Markdown | 7 | 7 / 7 |
| Mixed (Markdown + PDF (typed)) | 1 | 1 / 1 |
| PDF (typed) | 32 | 15 / 15 |
| PDF form (labels and values) | 10 | 10 / 10 |
| Plain text | 3 | 3 / 3 |
| Scanned PDF (read with OCR) | 3 | 2 / 3 |
| No document (must be refused) | 21 | 17 / 17 |

## Level by set

| Set | Level 1 | Level 2 | Level 3 | Level 4 | Level 5 | Run |
| --- | --- | --- | --- | --- | --- | --- |
| test | 6 / 6 | - | 4 / 4 | 3 / 3 | 7 / 7 | 2026-10-13, groq/openai/gpt-oss-120b |
| real | 10 / 10 | - | 3 / 3 | - | 5 / 5 | 2026-10-13, groq/openai/gpt-oss-120b |
| report | not run yet | not run yet | not run yet | not run yet | not run yet | not run yet |
| forms | 8 / 9 | 2 / 2 | 2 / 2 | - | 5 / 5 | 2026-10-13, groq/openai/gpt-oss-20b |

## Test set: 8 made-up company documents

| ID | Level | Format | Question | Passed |
| --- | --- | --- | --- | --- |
| t01 | 1 | PDF (typed) | What is the standard hotel cap per night under the expense policy? | yes |
| t02 | 1 | Markdown | How often must passwords be rotated? | yes |
| t03 | 1 | Plain text | How long is the free trial of Lumenfold Cloud? | yes |
| t04 | 1 | Markdown | How much does the Orbit B2 weigh? | yes |
| t05 | 1 | Plain text | When is the weekly VPN maintenance window? | yes |
| t06 | 1 | PDF (typed) | Within how many days must an expense claim be submitted? | yes |
| t07 | 3 | Markdown | How did the annual leave entitlement change between the 2024 and 2025 handbooks? | yes |
| t08 | 3 | Markdown | Which scanner has the longer battery life, the Orbit A1 or the Orbit B2, and what are the two figures? | yes |
| t09 | 3 | Plain text | What does the Enterprise plan cost per user per month, and how fast does Enterprise support respond? | yes |
| t10 | 3 | Mixed (Markdown + PDF (typed)) | How quickly must a lost device be reported, and how much is the home office allowance? | yes |
| t16 | 4 | Markdown | How many days of annual leave do employees get in 2025? | yes |
| t17 | 4 | Markdown | How long was the probation period under the 2024 handbook? | yes |
| t18 | 4 | Markdown | What is the IP rating of the Orbit A1? | yes |
| t11 | 5 | No document (must be refused) | Who is the CEO of Lumenfold Systems? | yes |
| t12 | 5 | No document (must be refused) | What is the stock ticker symbol of Lumenfold Systems? | yes |
| t13 | 5 | No document (must be refused) | What is the password for the guest Wi-Fi network? | yes |
| t14 | 5 | No document (must be refused) | What is the purchase price of the Orbit A1 scanner? | yes |
| t15 | 5 | No document (must be refused) | What is the capital city of Australia? | yes |
| t19 | 5 | No document (must be refused) | What is the annual leave entitlement in the 2026 handbook? | yes |
| t20 | 5 | No document (must be refused) | What is the battery life of the Orbit C3? | yes |

## Real set: the 88-page GDPR regulation

| ID | Level | Format | Question | Passed |
| --- | --- | --- | --- | --- |
| r01 | 1 | PDF (typed) | Within how many hours must a controller notify the supervisory authority of a personal data breach? | yes |
| r02 | 1 | PDF (typed) | What is the maximum administrative fine for the most serious infringements of the Regulation? | yes |
| r03 | 1 | PDF (typed) | From what age can a child give their own consent to information society services? | yes |
| r04 | 1 | PDF (typed) | From which date does the Regulation apply? | yes |
| r05 | 1 | PDF (typed) | How long does a controller have to respond to a request from a data subject? | yes |
| r06 | 1 | PDF (typed) | Which earlier directive does the Regulation repeal? | yes |
| r07 | 1 | PDF (typed) | Below how many employees is an organisation exempt from keeping records of processing activities? | yes |
| r08 | 1 | PDF (typed) | What is the lowest age that Member States may set by law for a child's consent? | yes |
| r09 | 1 | PDF (typed) | How does the Regulation define pseudonymisation? | yes |
| r10 | 1 | PDF (typed) | In which cases must a controller designate a data protection officer? | yes |
| r11 | 3 | PDF (typed) | What are the two tiers of maximum administrative fines in euros? | yes |
| r12 | 3 | PDF (typed) | How quickly must a data breach be reported to the supervisory authority, and what is the highest fine tier in euros? | yes |
| r13 | 3 | PDF (typed) | By how long can the deadline for answering a data subject request be extended? | yes |
| r14 | 5 | No document (must be refused) | What does the Regulation say about blockchain? | yes |
| r15 | 5 | No document (must be refused) | What is the maximum fine under the California Consumer Privacy Act? | yes |
| r16 | 5 | No document (must be refused) | How did Brexit change how the Regulation applies in the United Kingdom? | yes |
| r17 | 5 | No document (must be refused) | What salary must a data protection officer be paid? | yes |
| r18 | 5 | No document (must be refused) | Who won the 2018 FIFA World Cup? | yes |

## Report set: a 48-page student project report

| ID | Level | Format | Question | Passed |
| --- | --- | --- | --- | --- |
| p01 | 1 | PDF (typed) | Which language model does the offensive language detection project fine-tune? | not run |
| p02 | 1 | PDF (typed) | Which GPU was used to fine-tune the Distil-BERT model? | not run |
| p03 | 1 | PDF (typed) | Who guided the offensive language detection project? | not run |
| p04 | 1 | PDF (typed) | On what date was the viva-voce examination for the offensive language detection project held? | not run |
| p05 | 1 | PDF (typed) | What is the maximum input length, in tokens, that the offensive language detection system accepts? | not run |
| p06 | 2 | PDF (typed) | Into which four categories does the offensive language detection system classify text? | not run |
| p07 | 2 | PDF (typed) | Which framework and libraries are used to build and deploy the Distil-BERT content detection system? | not run |
| p08 | 2 | PDF (typed) | How much RAM and how much storage does the hardware specification for fine-tuning Distil-BERT call for? | not run |
| p09 | 2 | PDF (typed) | Which evaluation metrics are used to test the offensive language detection system? | not run |
| p10 | 2 | PDF (typed) | Which two interfaces does the offensive language detection system offer, and who is each one for? | not run |
| p11 | 3 | PDF (typed) | How does the offensive language detection system support languages other than English, and which external APIs does it use? | not run |
| p12 | 3 | PDF (typed) | What limitations does the conclusion of the offensive language detection project name, and what multimedia support is proposed as future development? | not run |
| p13 | 3 | PDF (typed) | What do existing offensive language detection systems struggle with, and what does the proposed system combine to handle implicit content? | not run |
| p14 | 4 | PDF (typed) | What batch size does the report recommend for training on the RTX 2050, and what batch size is set in the source code of the offensive language detection project? | not run |
| p15 | 4 | PDF (typed) | On which port does the Flask API of the offensive language detection project run, and on which port is the Gradio interface launched? | not run |
| p16 | 4 | PDF (typed) | What label and what confidence did the content detection system give the Hindi complaint about a useless service? | not run |
| p17 | 4 | PDF (typed) | How many training epochs does the configuration in the source code of the offensive language detection project specify? | not run |
| p18 | 5 | No document (must be refused) | What overall accuracy percentage did the offensive language detection model achieve on its test set? | not run |
| p19 | 5 | No document (must be refused) | How many hours did it take to train the offensive language detection model? | not run |
| p20 | 5 | No document (must be refused) | What grade was awarded for the offensive language detection project report? | not run |
| p21 | 5 | No document (must be refused) | How many text samples from Twitter are in the dataset of the offensive language detection project? | not run |

## Forms set: a filled-in form and a handwritten scan

| ID | Level | Format | Question | Passed |
| --- | --- | --- | --- | --- |
| f01 | 1 | PDF form (labels and values) | What is the preferred name of the patient on the intake form? | yes |
| f04 | 1 | PDF form (labels and values) | Who is the patient's emergency contact on the intake form? | yes |
| f05 | 1 | PDF form (labels and values) | What chronic conditions does the patient report on the intake form? | yes |
| f06 | 1 | PDF form (labels and values) | What is the reason for the patient's visit to Willow Creek Family Medicine? | yes |
| f07 | 1 | PDF form (labels and values) | How often does the patient exercise? | yes |
| f08 | 1 | PDF form (labels and values) | What is the patient's own phone number on the intake form? | yes |
| s01 | 1 | Scanned PDF (read with OCR) | What is the subject code written on the handwritten assignment cover page? | yes |
| s02 | 1 | Scanned PDF (read with OCR) | What is the topic of the handwritten assignment? | yes |
| s03 | 1 | Scanned PDF (read with OCR) | What date is written on the handwritten assignment cover page? | NO |
| f02 | 2 | PDF form (labels and values) | What is the patient allergic to, according to the intake form? | yes |
| f03 | 2 | PDF form (labels and values) | Which medications is the patient currently taking? | yes |
| f09 | 3 | PDF form (labels and values) | Who is the patient's insurance provider and what is the policy number? | yes |
| f10 | 3 | PDF form (labels and values) | What past surgeries has the patient had, and what does the family medical history say about her mother? | yes |
| f11 | 5 | No document (must be refused) | What is the patient's blood type on the intake form? | yes |
| f12 | 5 | No document (must be refused) | Which doctor examined the patient at Willow Creek Family Medicine? | yes |
| f13 | 5 | No document (must be refused) | How much is the patient's insurance co-payment for this visit? | yes |
| s04 | 5 | No document (must be refused) | How many marks were awarded for the handwritten assignment? | yes |
| s05 | 5 | No document (must be refused) | Which college issued the handwritten assignment? | yes |
