# Notes: newsapps

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

The app idea I had was one where users can either search for individual items or simply click on the rows in a table beneath the search bar. Those rows open up to the name of items in that category: Big Equipments opens up to elevators, trash dumpster, etc. I used the all_item_grouped.csv as the basis of my news app. I also linked documents, so that users may read through the documents themselves for more context.

A few things were wrong with the app.

One issue was that the details from the minutes, disolayed after each item, made no sense.
If I search for "door" for example, the excerpts from the pdfs should be displayed on the app to help the user know what was said about a door. 
The excerpts did show up, but rather than be comprehensive, they looked like this: 
...nstalled in the lobby to allow easier access into the activity roo...
I could tell the complete texts were not extracted, so I repeated the process and asked copilot to extract everything. That worked better.



While I have worked on some of the problems with the apps functionality, there are still some issues currently affecting user experience which i am working on, including, but not limited to the following:

I find that when I search for "window", doors also pop up. Actually, doors mostly pop up. There are more doors than windows in the responses I get, and I think it is because I grouped windows and doors together in the csv with which the app was built. 
The app also does not take me to a details page when I search for window, especially.

I named the pdf like this: Jan 21 (for January 2021) but this does not help users as far as dates are concerned. One may confuse Jan 21 and January 21st rather than January 2021. I intend to make the dates more clear to improve user experience.

Also, the UI can look better, but this is not the most pressing issue.
                                                               
