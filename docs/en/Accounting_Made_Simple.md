# Accounting Made Simple — for non-accountants

> For shop owners (and anyone who sells or supports the program). No accounting background needed.
> Goal: understand what the program shows you, explain it with confidence, and answer common questions.

---

## Lesson 1: five words that explain any shop

Imagine a shop called "Hope Grocery". Everything in it belongs to one of five boxes:

| Box | In shop language | Examples | Account number in the program starts with |
|---|---|---|---|
| **Assets** | What the shop owns | Cash in the drawer, bank balance, stock on the shelves, customer debts, fridges | **1** |
| **Liabilities** | What the shop owes others | What we owe suppliers, cheques we gave that haven't cleared, a loan, VAT payable, loyalty points customers haven't redeemed yet | **2** |
| **Equity** | The owner's share | Capital the owner put in + accumulated profits − what they took out | **3** |
| **Revenue** | What comes in from selling | Sales | **4** |
| **Expenses** | What it costs to run the shop | Cost of goods sold, rent, electricity, salaries, spoiled stock | **5** and **6** |

### The golden rule (the balance sheet equation)

```
What the shop owns  =  What it owes others  +  The owner's share
      Assets        =      Liabilities      +       Equity
```

**Example:** the shop has stock worth 50,000, cash 3,000 and customer debts 2,000 → assets 55,000.
It owes suppliers 5,000 → liabilities 5,000. So **the owner's share = 50,000**. That is "what my shop is worth".

> In the program: **Accounting & balance sheet → Balance sheet** shows these three figures at the top of the screen.

---

## Lesson 2: profit — gross and net

```
Sales
− Returns
= Net sales
− Cost of goods sold          (what we paid for what we sold)
= Gross profit                (profit on the goods themselves)
− Expenses (rent, electricity, salaries...)
− Stock losses (spoiled, expired, theft)
± Cash drawer shortage or overage
= Net profit                  (what really ends up in the owner's pocket)
```

**One-day example:** we sold 1,000. What we sold cost us 780 → gross profit 220 (22% margin).
We paid 60 for electricity and threw away expired labneh that cost 20 → net profit 140.

**Common mistakes shop owners make (the program avoids them):**
1. "I sold 1,000 today, so I made 1,000" → wrong; profit comes after the cost of the goods.
2. "The drawer has 500 more than this morning, so my profit is 500" → wrong; maybe you didn't pay a supplier, or a customer paid an old debt.
3. Forgetting discounts, returns and spoiled stock → profits that don't exist.

> In the program: **Reports → Profit & Loss**, or **Accounting → Income statement**. Both give the same net profit.

### Margin vs. markup (a very common question)
- You bought at 8 and sold at 10.
- **Markup** = 2 ÷ 8 = 25%.
- **Margin** = 2 ÷ 10 = 20%. ← this is what the program shows as "margin".

---

## Lesson 3: cost of goods and the "weighted average"

You bought 10 cans of tuna at 3, then 10 more at 4 (the price went up). What does one can cost?
**Weighted average** = (10×3 + 10×4) ÷ 20 = **3.5**.
The program updates each item's cost this way with every purchase invoice, so profits stay accurate even when prices change.

---

## Lesson 4: cash is not profit — drawer, bank and owner's account

- **Cash (1110):** the money actually in the cashier drawers.
- **Bank (1120):** card sales, transfers and cleared cheques.
- **Owner's current account (3120):** any money the owner takes from the drawer for themselves, or pays for the shop from their own pocket (such as rent paid outside the drawer).

**Why does it matter?** An owner who takes money from the drawer every day without recording it starts believing the shop is losing money, or that the cashier is stealing. The program records it automatically:
- A "cash withdrawal" from the cash screen → recorded on the owner's account.
- If you close a shift with 1,500 and open the next one with 200 → the program understands the owner took 1,300.
- An expense "not from the drawer" → paid by the owner from their own pocket.

---

## Lesson 5: debts and cheques

- **Customer receivables (1210):** the total customers owe you ("the credit book"). Credit sales increase it; payments reduce it.
- **Supplier payables (2110):** what we owe suppliers. An unpaid purchase invoice increases it; a payment reduces it.
- **Incoming post-dated cheque (1130):** a customer gave you a cheque dated later. Their debt goes down **immediately**, but the money hasn't reached the bank yet. On the due date:
  - **Cleared** → the amount moves to the bank.
  - **Bounced** → the debt goes back on the customer automatically.
- **Outgoing post-dated cheque (2120):** you gave a supplier a cheque. You owe the supplier less, but it is now a commitment on your bank account until it clears. **Watch the "cheques due within a week" alert so your cheque never bounces!**

---

## Lesson 6: double entry — why "debit" and "credit"?

Every transaction touches at least two accounts, and the **debit** side always equals the **credit** side. An easy rule:

- **Debit** = where the value went (an asset or an expense increased).
- **Credit** = where the value came from (a liability, revenue or equity increased, or an asset decreased).

| Transaction | Debit (went to) | Credit (came from) |
|---|---|---|
| Cash sale of 100 (cost 80) | Cash 100 / Cost of goods 80 | Sales 100 / Inventory 80 |
| Credit sale to Abu Ahmad, 50 | Customer receivables 50 | Sales 50 |
| Abu Ahmad paid 50 in cash | Cash 50 | Customer receivables 50 |
| Unpaid purchase invoice of 1,000 | Inventory 1,000 | Supplier payables 1,000 |
| Paid the supplier 400 from the drawer | Supplier payables 400 | Cash 400 |
| Electricity 60 from the drawer | Expenses – electricity 60 | Cash 60 |
| Threw away expired labneh costing 20 | Stock losses 20 | Inventory 20 |
| Owner put 20,000 capital in the bank | Bank 20,000 | Capital 20,000 |

> **The program writes all these entries by itself.** See them in **Accounting → Journal**.
> A manual entry is needed only for things outside buying and selling (capital, a loan, buying a fridge...), and there is a ready "Financial transaction" window: choose the transaction and type the amount.

---

## Lesson 7: the four accounting reports and the question each one answers

| Report | The question it answers | For whom |
|---|---|---|
| **Income statement** | Did I make a profit in this period? How much? | The owner |
| **Balance sheet** | What is my shop worth today? What do I own and what do I owe? | The owner, the bank when asking for a loan |
| **Trial balance** | Do all accounts balance? What is each account's balance? | The auditor, the tax office |
| **Account statement** | Every movement on one account (the bank, for example) with its balance | The owner and the accountant for reconciliation |

> **Tip:** at the end of the year, instead of paying the accountant for days to gather your books, print the trial balance and balance sheet from the program in a minute.

---

## Lesson 8: VAT (if the shop is registered)

- If prices **include VAT** (most common): a price of 116 at 16% → 16 is tax and 100 is revenue.
- VAT is not profit; it is money held for the state. So the program takes it out of revenue and puts it in **VAT payable (2210)**.
- VAT on purchases (input VAT) is entered with the purchase invoice from the supplier's invoice. The **VAT report** subtracts it from VAT on sales and gives you the net amount to pay.

---

## Lesson 9: stock counts and shortages

- **Stock count:** count the goods on the shelf and enter the real number. The program calculates the difference:
  - Less than expected → a **stock loss** (deducted from profit).
  - More than expected → reduces the loss.
- **Cash shortage:** when closing a shift you count the money; if it is less than expected, the shortage appears in the reports and in "Cash shortage (5130)".
- **Tip:** count expensive items (cigarettes, baby formula, oils) weekly, and do a full count every 3–6 months.

---

## Lesson 10: quick glossary

| Term | What it means |
|---|---|
| Receivables | Money customers owe us |
| Payables | Money we owe suppliers |
| Debit/credit balance | Assets and expenses normally have a "debit" balance; liabilities, revenue and equity a "credit" balance |
| Cost of goods sold | The purchase price of what we sold |
| Gross profit | Sales − cost of goods |
| Net profit | Gross profit − all expenses and losses |
| Working capital | Current assets (cash, bank, stock, debts) − short-term liabilities |
| Owner's account / drawings | What the owner took from the shop's money |
| Opening balances | What existed before using the program (stock, old debts) |
| FEFO | First expired, first out — sell what expires soonest first |
| Slow-moving items | Stock not sold for a while = frozen money |
| Average basket | The average invoice value; raising it with offers increases sales |

---

## Test yourself (answers below)

1. A shop has stock of 30,000 and cash of 2,000, and owes suppliers 7,000. What is the owner's share?
2. You sold 500, what you sold cost 400, and you paid 30 rent today. What are gross and net profit?
3. A customer gave you a cheque for 1,000 due in a month. Did your bank balance go up today?
4. You took 200 from the drawer for household expenses. Is that an expense of the shop?
5. Purchase price 4, sale price 5. What is the margin?

**Answers:** 1) 25,000. 2) Gross 100, net 70. 3) No; only the customer's debt went down, and the amount sits in "cheques under collection" until it clears. 4) No; it is a drawing on the owner's account and does not reduce the shop's profit. 5) 20%.
