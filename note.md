First, I downloaded all the available pdfs from 2021 to 2026 and put them in a folder. Then I had copilot produce an extraction script. Because of some inconsistencies in labelling the comments I was interested in, I let copilot know that some comments were labelled under different headers depending on the year. E.g: resident comments under "resident comments" some years and "comments-tenants and general public" other years OR "executive directors reports" some years and "chief executive officers reports" other years.

Next, I ran the script with a groq model to keep the data secure. The extraction came in 57 different json files, because there were 57 pdfs. I had copilot merge them in one json file.
One thing I noticed is that it did not extract the entire text for the sections I requested, it summarized some. Not sure how this affects the entire process, but we'll see.

Up Next: Look through the extracted document and decide if you want to use jus the summaries for your app, if you want to extract all household items mentioned in the json and put them in groups, or how you want your app to work, generally.

NEXT DAY
First, I want to extract all household items that have been mentioned in the document. Copilot wrote a script for that and I ran the extraction with Groq.
After the extraction, I could identify these items that came up frequently;
Elevator
Pest control
Generator
Food bank
HVAC
Cameras
Garden (water in the garden)

When I spot checked, I saw faucets, handicap handles which suggested everything was not extracted. So we tightened the prompt and got a lot more items. Now, I have more items in the all_items_grouped csv. It places all extracted items un groups, so I can see what fall under big, small, other equipment.
I noteiced there are some misclassifications. Appliances as a header has parking pemrits underneath, for example. Will need to figure out reclassification.

Up Next: Reclassify csv. Will you do this manually?
Figure out next steps for your app.