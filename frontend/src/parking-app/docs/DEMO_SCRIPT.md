# GenFabTools Parking Engine — 5-Minute Demo Script

**Version:** 1.0.0  
**Audience:** External stakeholders, potential beta users  
**Duration:** ~5 minutes  

---

## Opening (30 seconds)

> "Thanks for joining. Today I'm going to show you the GenFabTools Parking Engine — a tool we built to help you answer one question early in a project:
>
> **How many parking stalls can I realistically fit on this site?**
>
> This isn't a design tool. It doesn't produce construction documents. What it does is give you a fast, transparent estimate so you can make better decisions before committing to a design direction."

---

## What Problem Does This Solve? (45 seconds)

> "If you've ever been in a planning meeting where someone asks 'Can we fit 80 stalls on that lot?' — you know the answer is usually 'Let me get back to you.'
>
> Then someone spends a day sketching layouts, and it turns out the answer is 62 stalls because of the site shape.
>
> This tool gives you that answer in seconds. Not a final answer — a working estimate you can use to evaluate options, compare scenarios, and have informed conversations."

---

## Live Demo — Creating a Scenario (90 seconds)

> "Let me show you how it works.
>
> On the left, I enter my site dimensions. Let's say I have a lot that's 300 feet by 200 feet. I'll type those in and click 'Create Site.'
>
> [Enter 300 × 200, click Create Site]
>
> The site appears in the center view. Now I can configure the parking type.
>
> For this demo, I'll use surface parking with two-way aisles — that's the most common setup for a commercial lot.
>
> [Select Two-Way Aisles]
>
> And I'll set a 5-foot setback from the property line.
>
> [Set setback to 5]
>
> The tool automatically evaluates and shows results on the right."

---

## Reading the Results (60 seconds)

> "Here's the result: 157 stalls.
>
> That includes 153 standard stalls and 4 ADA-accessible stalls. The ADA count is calculated based on generic U.S. parking standards.
>
> Below that, you can see the efficiency: about 380 square feet per stall. That's typical for a two-way aisle layout.
>
> The usability ratio shows that 93% of the site area can actually be used for parking — the rest is lost to the setback and the site edges."

---

## Explaining the Result (60 seconds)

> "Now, here's where transparency matters.
>
> If I scroll down, there's a section called 'How This Result Was Generated.'
>
> [Scroll to expand How Generated panel]
>
> This tells you exactly what assumptions went into the calculation:
>
> - Standard stall size: 9 feet by 18 feet
> - Two-way aisle width: 24 feet
> - The setback I chose: 5 feet
>
> There's no hidden logic. If you see a number, you can trace where it came from.
>
> And if you're wondering 'Why didn't I get more stalls?' — there's a hint right here that explains the main factor. In this case, it's the aisle width taking up space."

---

## Trust and Limitations (45 seconds)

> "A few things to be clear about.
>
> First, this is a conceptual estimate. The number you see is based on generic rules — not local zoning codes, not ADA-specific requirements for your jurisdiction, not your architect's preferred layout.
>
> Second, this tool does not produce drawings you can submit for permits. It's for early feasibility — before you bring in the full design team.
>
> Third, we show you the assumptions because we want you to trust the output. If something looks wrong, you can see why and adjust.
>
> The footer at the bottom says it clearly: 'Conceptual estimates only. Not for construction.'"

---

## Closing (30 seconds)

> "That's the GenFabTools Parking Engine.
>
> It's fast. It's transparent. And it helps you answer 'How many stalls?' without waiting for a full study.
>
> We're looking for feedback from teams who deal with parking feasibility regularly. If that's you, we'd love to hear what works and what doesn't.
>
> Any questions?"

---

## Demo Checklist (Before Presenting)

- [ ] Backend server is running on port 8001
- [ ] Frontend is loaded at correct URL
- [ ] Start with no existing scenarios (fresh state)
- [ ] Have backup screenshots in case of network issues
- [ ] Test the 300×200 scenario before the call
