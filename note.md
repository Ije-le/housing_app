First, I downloaded all the available pdfs from 2021 to 2026 and put them in a folder. Then I had copilot produce an extraction script. Because of some inconsistencies in labelling the comments I was interested in, I let copilot know that some comments were labelled under different headers depending on the year. E.g: resident comments under "resident comments" some years and "comments-tenants and general public" other years OR "executive directors reports" some years and "chief executive officers reports" other years.

Next, I ran the script with a groq model to keep the data secure. The extraction came in 57 different json files, because there were 57 pdfs. I had copilot merge them in one json file.
One thing I noticed is that it did not extract the entire text for the sections I requested, it summarized some. Not sure how this affects the entire process, but we'll see.

### Up Next: Look through the extracted document and decide if you want to use jus the summaries for your app, if you want to extract all household items mentioned in the json and put them in groups, or how you want your app to work, generally.

### NEXT:

First, I extracted all household items that have been mentioned in the document. Copilot wrote a script for that, and I ran the extraction with Groq.
After the extraction, I could identify these items that came up frequently;
Elevator
Pest control
Generator
Food bank
HVAC
Cameras
Garden (water in the garden)

When I spot checked, I saw faucets, handicap handles which suggested everything was not extracted. So we tightened the prompt and got a lot more items. Now, I have more items in the all_items_grouped csv. It places all extracted items in groups, so I can see what falls under big, small, other equipment.
I noticed there are some misclassifications. Appliances as a header has parking pemrits underneath, for example. Will need to figure out reclassification.

### Up Next: Reclassify csv. Will you do this manually? Figure out next steps for your app.


I have manually cleaned all_items_grouped.csv and I have names of items under the category groups that I want. I want to make a news app, where users can search for items and see how many times they've been mentioned throughout the period. I also want the app to have a table with a set of rows beneath the search bar like this: HVAC, Big equipment, small equipment ..
The idea is the people can either search for individual items or simply click on the rows in the table. Those rows open up to the name of items in that group: boiler, radiatos, vent, etc
When a user clicks on the items, they are moved to a details page, where the can see all the times that item has come up in meetings with dates, and a summary of what was discussed about the item.
What would be the steps to do this?

### Next:
I manually removed all the entries I did not want from the grouped csv. Then I realized that it could not be the basis of my app because I needed it to be more detailed, people had to know how many times an item was mentioned and wht happened those times. So using copilot, I cleaned the initial csv from which I got the grouped csv. We made that into a third csv. This third csv was produced after using the grouoed one as an allow list, so things that did not fall under the categories we had here were weeded out [re-read this an rephrase if needed.]
This new csv is the basis for the app.

 ### Up Next:
Clean up the app.
Check the csv and see what's missing.
Why do the details of the meetings not make any sense?

## Next
When I type an item in the search bar, I want to immediately see all the times that they were mentioned right under the search bar