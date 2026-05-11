First, I downloaded all the available pdfs from January 2020 to March 2026 and put them in a folder.
My plan was to get a list of all household items and create an app that allowed a user search for those items and see what had been discussed about them in meetings.
There was no real way to know all the household items mentioned during meetings within this period by nereky looking, so I had copilot produce an extraction script, extract_items.py, that would extract all household items and appliance that had been metioned in the meetings since 2020.

There were some problems with this process:

The structure of the meeting minutes had changed over time. The section that held residents comments (which was where most of the complaints about household items were recorded) was labelled "Resident Comments" in some years and "Comments -Tenants and General Public". Another relevant section, which had details on what the Housing Authority is doing about those complaints, had also been changed over time. It was labelled "Executive Directors Report" in some years, and "Chief Executive Officers Report" in other years
I gave copilot a guide, so that it would note these changes while carrying out the extraction. I asked it to extract specific parts of the minutes that were relevant to the app, including dates, residents comments, executive directors comments.

Next, I ran the script with a groq model to keep the data secure, especially because people were named in these documents. The extraction came in 57 different json files, because there were 57 pdfs. I wanted them in one pdf, so I had copilot merge them in one json file: all_meetings.json. I used groq for this extraction.
I generated two csvs from this process: one more deatiled csv, another, a csv that h ad otems grouped together.
After the extraction, I could identify these items that came up frequently;
Elevator
Pest control
Generator
Food bank
HVAC
Cameras

When I spot checked through the pdfs themselves, I saw faucets, handicap handles and some other appliances appeared in the documents,  but not in my list of extracted items, which suggested that not everything was extracted.
So I tightened the prompt and got a lot more items in the all_items_grouped csv. It places all extracted items in groups, so I can see what falls under big, small, other equipment.
There were some misclassifications for example, "Appliances" as a header has parking pemrits underneath. So I manually cleaned the all_items_grouped.csv and placed names of items under the category groups that I want. I also created new categories where I felt they were missing.

The app idea I had was one where users can either search for individual items or simply click on the rows in a table beneath the search bar. Those rows open up to the name of items in that category: Big Equipments opens up to elevators, trash dumpster, etc. I used the all_item_grouped.csv as the basis of my news app.

                                                               

# to conclude:
why?
what csv did you use instead?
when you saw the details page did not show full sentences, what did you do to clean it up.
What are the problems with the app currently? the UI is not that great...









### Up Next: Reclassify csv. Will you do this manually? Figure out next steps for your app.


I manually cleaned the all_items_grouped.csv and I have names of items under the category groups that I want. I want to make a news app, where users can search for items and see how many times they've been mentioned throughout the period. I also want the app to have a table with a set of rows beneath the search bar like this: HVAC, Big equipment, small equipment ..
The idea is the people can either search for individual items or simply click on the rows in the table. Those rows open up to the name of items in that group: boiler, radiatos, vent, etc
When a user clicks on the items, they are moved to a details page, where the can see all the times that item has come up in meetings with dates, and a summary of what was discussed about the item.
What would be the steps to do this?

### Next:
I manually removed all the entries I did not want from the grouped csv. Then I realized that it could not be the basis of my app because I needed it to be more detailed, people had to know how many times an item was mentioned and wht happened those times. So using copilot, I cleaned the initial csv from which I got the grouped csv. We made that into a third csv. This third csv was produced after using the grouped one as an allow list, so things that did not fall under the categories we had here were weeded out [re-read this an rephrase if needed.]
This new csv is the basis for the app.

 ### Up Next:
Clean up the app.
Check the csv and see what's missing.
Why do the details of the meetings not make any sense?

## Next
When I type an item in the search bar, I want to immediately see all the times that they were mentioned right under the search bar