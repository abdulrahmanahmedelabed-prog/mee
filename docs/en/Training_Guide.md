# Complete Training Guide

> **Who is this for?** Shop owners, managers and cashiers. Every part is written step by step.
>
> **Practice without fear:** open **"Training copy"** from the Windows Start menu, or from inside the program: the **🎓 Training copy** link on the login screen or the **🎓 Training copy** button on the Help screen (it opens in a separate window while your program stays open). It contains a complete demo supermarket with **3 years of trading history** (daily sales with seasons, shifts, purchases, debts, cheques, e-payments), stored separately so it **never touches your shop's data**. The first launch takes a minute or two to prepare.
> Training copy logins: `admin` / `admin` (administrator) or `cashier` / `1234` (cashier).
> It also includes **online orders** for the last two months in every status, **former employees** with their salaries and payslips, and **three branches** (Hebron, Ramallah and Nablus) that appear together in the branches report.
>
> **Intro video:** Help → **🎬 Intro video** (one minute).
>
> **Switching language:** the **🌐 العربية / English** button at the top switches the whole interface instantly.

---

## Contents

1. [Key concepts in 5 minutes](#1)
2. [Installation and first run](#2)
3. [Plans and activation](#3)
4. [A cashier's working day](#4)
5. [Manager and owner tasks](#5)
6. [Mobile: the app, owner dashboard and online store](#6)
7. [Hands-on exercises](#7)
8. [FAQ and troubleshooting](#8)

---

<a id="1"></a>
## 1. Key concepts in 5 minutes

| Concept | Meaning |
|---|---|
| **Roles** | **System administrator** (everything), **Store manager** (everything except settings and users), **Cashier** (sales, invoices, customers, cash drawer) |
| **Manager approval** | If a cashier needs a restricted action (big discount, price change, exceeding a credit limit), a window appears where the manager types their name and password on the spot; it is recorded in the activity log |
| **Shift** | A cashier's working period on one till: it starts with the cash in the drawer and ends with counting the cash. It reveals shortages and overages |
| **Unit** | Each item has a base unit (piece) and can have larger units (carton = 24 pieces) with their own barcode and price |
| **Batch** | A quantity of an item with one expiry date. The program sells the soonest-to-expire first |
| **Credit** | Selling on account to a registered customer (the credit book) |
| **Main and secondary tills** | In shops with several cashiers: one main computer keeps the data, the others connect to it over the shop network |

**Important rule:** everything is saved immediately — there is no general "Save" button. A backup is taken automatically every day and when the program closes.

---

<a id="2"></a>
## 2. Installation and first run

### 2.1 Installation
1. Run **ShopAccounting-Setup** → Next → Install.
2. A program shortcut appears on the desktop, and a **"Training copy"** shortcut in the Start menu.
3. On first run Windows Firewall may ask: choose **Allow** (needed for other tills and for phones).

### 2.2 First login
1. User `admin`, password `admin`.
2. The program asks you to **change the password immediately**. Choose one you'll remember and keep it with the owner.
3. The **first-time setup wizard** appears:
   - Shop name, phone, address, currency, country and VAT.
   - **Shop type:** "Small shop" opens the simple mode (sales, inventory, debts, reports); "Supermarket or large shop" opens all screens. You can change this later.
   - **Touch-screen till:** if the cashier computer has a touch screen.
4. Click **Start ✓**.

### 2.3 Preparing your data (the most important hour with the program)
In this order:
1. **Users:** Settings → Users → "+ User" for each cashier (role: cashier).
2. **Printer:** Settings → Printing & cash drawer → choose the printer and paper width (80 or 58 mm) → "Preview a test receipt".
3. **Shop logo (optional):** Settings → Shop details → **🖼 Choose logo...** Any image works; the program prepares a color version for screens and A4 reports and a black-and-white one for the receipt printer.
4. **Products** — three ways:
   - **Fastest:** Inventory → **📤 Export to Excel** to get a file with the right columns, fill it with your items, save it as **CSV UTF-8**, then **📥 Import from Excel**.
   - **By scanning:** in the point of sale scan any unknown barcode → the program asks "Add it as a new product?".
   - **Manually:** Inventory → **+ New product**.
5. **Items without a barcode** (bread, vegetables): in the product card click **Generate** for an internal barcode, and tick "Favorite" to show it as a quick button in the point of sale.
6. **Weighed items:** for butchers and greengrocers, put the **scale code (PLU)** in the product card, using the same number programmed in the scale.
7. **Cartons:** in the product card → "+ Add unit": carton, 24 pieces, the carton barcode, its price.
8. **Your old credit book:**
   - Customers → **📥 Import credit book from Excel** → "Save empty template".
   - Fill in the template (name, phone, address, current debt, credit limit), save it as **CSV UTF-8**, then import it.
   - Duplicate names are skipped, and any error is shown with its line number.
   - Do the same for suppliers from the suppliers screen.
9. **Capital and bank (optional):** Accounting → "Financial transaction" → "Opening bank balance" or "Capital deposit".

---

<a id="3"></a>
## 3. Plans and activation

For the **first 30 days you get the full 👑 Max plan free** (every feature, unlimited tills). After that the program runs on the **🌱 Free plan**: selling, inventory, debts and basic reports **never stop**, and advanced features show a 🔒 lock. To upgrade to ⚡ Plus, 💎 Pro or 👑 Max you need an "activation key" for your computer, sent by your program provider.

- **To see your plan and compare plans:** click the plan badge at the top (for example "👑 Max • 23-day trial") or the **💎 Plans & upgrade** button.
- **What each plan includes:** Free covers selling, inventory, debts and reports; Plus adds the smart advisor, smart reordering, offers, cheques, installments and stock counting from the phone (the mobile app for price checks is available on every plan); Pro adds accounting, the financial audit, payroll, the online store, the owner dashboard and zakat; Max adds the shop assistant and branches.

**Activation steps (from an administrator account):**
1. Click **💎 Plans & upgrade** → **🔑 I have an activation key**, or Settings → **License & activation**. (Or click **"Get Pro"**, for example, in the plan comparison — the request reaches your provider on WhatsApp.)
2. **This device's code** appears (like `4F1A-9C03-7B2E-D5A8`). Click **📱 Request activation via WhatsApp**; the message is ready with the device code and shop name. (Or **📋 Copy** and send it any way you like.)
3. Your provider sends you the **activation key**: a long text starting with `SA1.`
4. Copy the whole key, paste it in the box and click **✓ Activate**.
5. The message "Activated successfully ✓" appears.

**Important:**
- The key works on **this computer only**. If you change computers, send the new device code to your provider.
- In shops with several tills: activate **the main computer only**; the others follow it.
- If a subscription ends, the program returns to Free: **selling never stops**, your data, reports and debts stay available, and your features come back as soon as you renew.

---

<a id="4"></a>
## 4. A cashier's working day

### 4.1 Start of shift
1. Log in with your own name (not the manager's).
2. The first sale asks you to **open a shift**: count the cash in the drawer (the change) and type the amount → **🔓 Open shift**.
3. Anything that takes cash out of or puts cash into the drawer (a debt paid in cash, paying a supplier from the drawer, an expense from the drawer, a cash refund) needs an open shift, so the cash count at the end of the day matches what really happened.

### 4.2 Selling — the fast way
| You want to | Do this |
|---|---|
| Add an item | Scan the barcode (or type part of the name and press Enter) |
| 3 pieces at once | Type `3*` then scan the barcode |
| A weighed item | Scan the scale label — the weight is read automatically |
| Increase/decrease quantity | **+** or **−** |
| Remove a line | **Delete** |
| Type a quantity | **F8** |
| Carton instead of piece | Scan the carton barcode, or **F5** on the line |
| A different price | **F10** (cashiers need manager approval) |
| Invoice discount | **F9** (amount or percentage; above the limit it needs manager approval) |
| Customer asks "how much is this?" | The **🔍 Price check** button — not added to the invoice |
| Exact cash, no window | **F12** |
| Pay | **F2**, or **Enter** with an empty search box |
| No small change | The **⬆ Whole number** button under the total: 19.40 becomes 20.00 (see below) |

**⬆ Whole number (round up):** rounds the invoice total up to the next whole number so the cashier doesn't need small change. Make it the default for every invoice in Settings → Sales & inventory, and switch it off for a single invoice with the same button.
- **In the books:** the difference (0.60, for example) is not added to item prices or their VAT; it goes to a separate account, **"Invoice rounding differences"**, under other income, so VAT stays correct and every item keeps its price.
- **On the receipt:** a "Rounding" line appears before the total.
- **On returns:** a partial return refunds item prices only; returning the whole invoice also refunds the rounding and reverses it from its account.
- **In the audit:** the auditor checks that every rounding is below 1, and flags a cashier who rounds far more often than colleagues.

**Offers apply themselves:** if an item has an offer (such as "buy 2 get 1 free") a 🎁 line appears under the total with the discount. You don't need to do anything.

### 4.3 The payment window
1. **Cash:** type what the customer gave you, or click a banknote button (10, 20, 50...). The **change** appears in large digits.
2. **Card:**
   - If the card terminal is connected to the program: click **💳 Pay by card on the terminal**. The amount goes to the terminal and the customer taps or inserts the card. When approved, the payment is recorded and the approval code is printed on the receipt. If declined, the bank's message appears and you choose another method.
   - Without a connection: type the amount on the bank terminal, then in the "Card / transfer" field (or "Full amount by card").
3. **E-wallet or banking app:** click the method's button (such as **📲 PalPay**). You and the customer (on the customer display) see your account number, a QR code and the amount. The customer pays in their app and shows you the confirmation: check the amount and your shop's name, type the **transaction number**, then **✓ Payment received**. If part is paid in cash, type it in the cash field first; the rest goes to the wallet.
4. **Split:** part cash and part card or wallet.
5. **Another currency** (if the manager enabled it): the 💱 button for the currency → type what the customer paid in it, and the program calculates the change in the shop's currency.
6. **On credit:** choose the customer first (**F4**), then "Rest on the customer's account" or "Full amount on credit".
7. **Enter** completes the sale. The receipt prints if printing is on, and the cash drawer opens.

> On touch screens a large number pad appears in the payment window.

### 4.4 Regular customers and loyalty points
1. **F4** → search by name or phone (or "+ New customer").
2. The button shows the customer's debt and 🎁 points.
3. To redeem points: the **🎁 Redeem points** button → type the number of points → it is deducted from the invoice.
4. After the sale "🎁 +25 points" appears and the points are printed on the receipt.
5. "Wholesale" customers: when selected, prices switch to wholesale prices automatically.

### 4.5 Everyday situations
| Situation | Solution |
|---|---|
| The customer forgot something and will come back | **F6 Hold** the invoice, serve the next customer, then **F7** to recall it |
| Print the last invoice again | **F11** |
| Open the drawer to give change | The **💰 Open drawer** button (recorded in the activity log) |
| An expired item shows a red ⛔ warning | Don't sell it; tell the manager to write it off from the expiry screen |
| The customer wants to return an item | Invoices & returns → search by invoice number → **↩ Return** → choose the quantity (the refund uses **the selling price on that invoice**, even if the item's price changed since, and the same discount ratio) → refund method: cash, against their debt, **to the card** or **to the same wallet** if the invoice was paid that way (the program suggests the original payment method, and never refunds more to a card or wallet than was paid with it). If the invoice was on credit and they still owe money, don't refund more cash than they paid: choose "Against the debt" |
| A customer pays off a debt | Customers → select them → **💰 Receive payment** |
| A customer gives a cheque for their debt | Customers → select them → **📥 Receive cheque** (needs manager permission) |
| An online order is ready for pickup | 🛵 Online orders → **🧾 Convert to invoice** → pay as usual |

### 4.6 If the network goes down (shops with several tills)
- A yellow "⚠ Offline mode" bar appears, and you **keep selling** in cash, by card or by wallet.
- **Not possible while offline:** credit sales, choosing a customer, loyalty points, returns.
- When the connection returns, invoices move **by themselves** to the main computer with their original times, without duplicates.

### 4.7 End of shift
1. Cash & shifts → **🔒 Close shift and count cash**.
2. Count the cash by denomination (200, 100, 50...) — the program adds it up. Foreign currency is counted at its value in the shop's currency.
3. The **expected**, **counted** and **difference** (shortage or overage) appear.
4. **🖨 Print the shift report** and hand it with the cash to the manager.

> **Golden rule for cashiers:** never take money from or put money in the drawer without recording it: use **⬆ Cash withdrawal** or **⬇ Cash deposit** with a reason. Otherwise a shortage or overage will appear under your name.

---

<a id="5"></a>
## 5. Manager and owner tasks

### 5.1 Every morning (5 minutes)
1. **🤖 Smart advisor:** recommendations ordered from most serious (⛔ red) to positive (✅ green). Each has a link to the right action: a profitable item about to run out, stock close to expiry, a customer who stopped buying, a repeated cash shortage...
2. **Dashboard:** yesterday's sales, low stock, expiry, **cheques due within a week**.
3. **Expiry:** write off expired goods, and put items close to expiry on offer.

### 5.2 Receiving goods from a supplier
1. Suppliers & purchases → **🧾 New purchase invoice** → choose the supplier.
2. Scan each item's barcode (or the carton barcode to buy by the carton).
3. Adjust the quantity, unit cost and sale price, and type the **expiry date** (e.g. 2027-03-31) for food items.
4. If you are VAT-registered: "Of which VAT" → type it from the supplier's invoice or "Calculate at the VAT rate".
5. "Pay the full amount" or type what you pay now; the rest becomes a debt to the supplier.
6. **Save invoice**: stock increases and costs update automatically.

### 5.3 Returning goods to a supplier
Suppliers → choose the supplier → **↩ Return to supplier** → scan the items → quantity and agreed price (excluding VAT) → reason → save. It is deducted from stock and from the supplier's account.
If VAT is enabled, a **"Supplier refunds the input VAT on it"** tick appears: leave it on if the purchase invoice included VAT, so the supplier is credited with the price plus VAT and input VAT goes down in the VAT return.

### 5.4 Smart reordering (instead of walking the shelves with pen and paper)
**The idea:** the program knows how much of each item you sell per day, so it works out what to order from each supplier and how much, instead of guessing.
Three steps at the top explain it: **📈 measures sales speed → 🧮 suggests the quantity → 📱 you send it to the supplier.**
1. 🧠 Smart reordering → the sentence: "Base it on sales from the last **30 days**, and order enough for **14 days**" → **🔄 Calculate order**.
2. Four cards appear: **🚨 Urgent** (out of stock or running out within 3 days), **📦 Items to order**, **💰 Estimated order value**, and **🚚 Suppliers**.
3. The table is sorted by urgency: red row = out or running out within 3 days, yellow = within a week, white = normal. For each item: in stock, daily sales, days it lasts, and the suggested quantity **rounded to cartons**.
4. **Edit a quantity** by double-clicking its cell if you want (a supplier offer, for example), and remove what you don't need.
5. Choose the supplier → **📱 Send the order to the supplier (WhatsApp)** — the message is ready with items and quantities.
6. When the goods arrive: **🧾 Convert to purchase invoice** — items and quantities are filled in; adjust prices and save.

### 5.5 Inventory and stock counts
- **📋 Stock count:** type the real quantity on the shelf; the difference is recorded automatically (less = loss). You can also count from a phone (part 6).
- **± Adjust quantity:** for damage, gifts or own use. Any decrease without an invoice counts as a loss in the profit report, and any increase as a gain. The exception is "Goods received" (goods that arrived without a purchase invoice); it's always better to record goods with a purchase invoice.
- **Changing the cost in the product card:** revalues the quantity in stock, and the difference shows as profit or loss in the reports.
- **Deleting an item that still has stock:** the remaining quantity is written off as a loss. If the goods really exist, don't delete it; edit its details instead.
- **📜 Item movements:** everything that came in and went out, and who did it.
- **🏷 Print labels:** price labels with barcodes.
- **🏷 Labels waiting to print (never forget a label):** any item whose price changes — by editing it, by the bulk price update or from a purchase invoice — joins the **label queue** automatically, and the count shows on the button. Click it → labels print for those items only → each item leaves the queue once printed. If an old label stays on the shelf for more than two days, the **Smart advisor** warns you and the **financial audit** records it (the shelf price differs from the till price).
- **Low stock only:** the list of items at their minimum.

### 5.6 Prices
- **Wholesale price:** "Wholesale price" in the product card, and "Price level: wholesale" in the customer card.
- **Bulk price update** (after suppliers raise prices): Smart advisor → Bulk price update → "Target margin", e.g. 20% → "Only items with a lower margin" → round to the nearest 0.50 → **👁 Preview** → **✓ Apply**. The program then offers to **print labels for the items that changed** right away; if you postpone, they wait in the label queue.
- **Raised a price and a customer returns an item bought before the increase?** They're refunded **the price on their original invoice**, not the new one, and the stock returns at its original cost. Neither the customer nor the shop gains or loses from the price change.
- **Changing a price at the till (F10):** each line keeps **the original price**, **the price it was sold at** and the cashier's name. In the books, revenue is recorded at the actual price (which is correct), and the difference appears in the **financial audit** as a management discount: "Manual price reductions at the till" with its total, its share of sales and the cashiers ranked, and "Sold above the original price" if a customer was overcharged. Every change is also in the activity log.
- **🏷 Pricing calculator:** next to "Sale price" in the product card press **🏷 Pricing**: enter the unit cost (or carton cost ÷ pieces) and the target profit (% on cost or % of the sale price), pick the rounding (for example up to the nearest 0.25) and you get the price incl. VAT and the unit profit; then **✓ Use this price**. Or type a price to see your profit. In a purchase invoice: select the line ← **🏷 Price line**.
- **Math inside fields:** in any amount field type `24*1.25`, `100+16%` or `250-10%` then Enter. The full calculator is the **🧮** button at the top or **Ctrl+=**: calculate, then **⤵ Insert into field** puts the result into the last field you were in.
- **ABC analysis:** never let A items (80% of your sales) run out. Reduce quantities of C items.
- **Bought together:** place the two items side by side or put them on a joint offer.

### 5.7 Debts
- **Customers & debts:** a statement for each customer, **🖨 Print statement**, **💬 WhatsApp reminder**, and **📣 Remind all debtors** (one message to each debtor in one click).
- **Credit limit:** in the customer card. The program blocks going over it without manager approval.
- **⚖ Adjustment:** forgiving a small amount or a correction (shown as an adjustment in the reports).
- **📅 Installments:** split a customer's debt into payments (monthly, every two weeks or weekly) and set the first due date. Payments are received with "Receive payment" as usual and are applied to the oldest installment first, so you see what's paid, overdue and upcoming. **💬 Installment reminder** sends the customer the amount and due date, and the smart advisor alerts you to late payers. Print the schedule for the customer to sign.

### 5.8 Cheques
- **Receiving a cheque from a customer:** 🏦 Cheques → 📥 → customer, amount, number, bank, due date.
- **Giving a cheque to a supplier:** 📤 → supplier... (or from the suppliers screen → "📤 Post-dated cheque").
- **On the due date:** select the cheque → **✓ Cleared in the bank**, or **↩ Bounced** (the debt comes back automatically).
- Colors: 🟥 past due and not updated, 🟧 within a week.

### 5.9 Offers and loyalty points
- 🎁 Offers & loyalty → **+ New offer**:
  - **Buy and get free:** the item, buy 2, get 1.
  - **Quantity for a fixed price:** 3 pieces for 10.
  - **Percentage off:** on an item or a **whole category** (e.g. detergents 15%).
  - Start and end dates; the offer stops by itself.
- **Loyalty points:** Settings → Loyalty points & owner dashboard. Recommended example: 1 point per 1 unit of currency, a point = 0.05, minimum redemption 100 → the customer gets 5% back.
  - In the accounts, points customers haven't redeemed are **a liability of the shop** shown on the balance sheet ("Loyalty points owed to customers"), and their cost appears in the profit report when earned, not when redeemed. This way profit never looks higher than it really is.

### 5.10 E-payments (wallets and banking apps)
**Setup (once):** Settings → **E-payments** → **✨ Suggestions for my country** (or "+ Add payment method"):
- The **name** customers know it by, and the **account number, phone or alias** they transfer to.
- **Money arrives in:** "Wallet balance" for mobile wallets, or "Bank account directly" for instant bank transfers.
- **QR code text (optional):** if the shop has an official QR code in the wallet app, put its text here to show it to customers. Without it, a code with the account number is shown.
- It's best to enable "Cashier must enter the transaction number".

**Reconciliation (weekly):** Reports → **E-payments**: the total of each method (sales + debt payments). Select a method to see its transactions with each transaction number, and match them with the wallet or bank statement. Any transaction in the program that's not on the statement = a fake confirmation or a mistake; check it immediately.

**Moving wallet balance to the bank:** Accounting → **➕ Financial transaction** → "Transfer e-wallet balance to the bank" with the amount that reached the bank, then "Fee deducted by the e-wallet" with the difference. The "E-wallets" balance on the balance sheet should equal your balance in the app.

> **Important for cashiers:** don't hand over the goods before you see the correct payment confirmation on the customer's phone. Screenshots can be faked; the weekly reconciliation catches that.

### 5.11 Expenses
💸 Expenses → type (electricity, rent...) → amount → "From the drawer" if paid from the till; untick it if the owner paid from their pocket or from the bank.
An expense paid from the drawer of a closed shift can't be deleted (its cash count is done). If it was a mistake, record a "Cash deposit" of the same amount in the current shift.

### 5.11.1 Employees and payroll
👔 **Employees & payroll** → **+ New employee** (name, job, monthly salary).
- **💵 Advance:** money the employee takes in advance. It isn't an expense but a debt deducted from their salary.
- **🧾 Pay salary:** choose the month → base + bonus − deductions (absence, lateness) → the program suggests deducting advances → net paid → in cash from the drawer or from the bank. A **payslip** prints for the employee to sign.
- The salary appears in expenses and the profit report, and what is paid from the drawer is deducted from the shift's expected cash.
- **An old payslip:** select the employee → **🖨 Payslip** → pick the month from the list. Or in the "History" table at the bottom: select the month's row → **🖨 Payslip for selected month**.
- **📄 Print employee statement:** all their salaries, advances and what was deducted, with dates and amounts.
- **Former employees:** make an employee who left "inactive" with **✏ Edit** (never deleted, so the record is kept). To see them: tick **"Show former employees"**.

### 5.12 Reports (what to read and when)
| Report | When | What to look for |
|---|---|---|
| Profit & Loss | Weekly and monthly | Net profit, margin (15–25% is good for a grocery) |
| **Period summary** (daily/weekly/monthly/yearly) | End of each week, month and year | Compare periods: where profit went up or down, and how payment methods change. Choose "Last 3 years" and "Yearly" to see the shop grow |
| E-payments | Weekly | Reconcile each wallet and banking app with its statement |
| Best sellers (by profit) | Monthly | What really earns you money; never let it run out |
| Slow-moving items | Monthly | Frozen money: put them on offer or return them to the supplier |
| Peak hours | When planning staff hours | When you need an extra cashier |
| By cashier | Weekly | Too many discounts from one cashier |
| VAT | When filing the return | VAT on sales − VAT on purchases = net payable |
| Activity log | When in doubt | Who changed a price, who opened the drawer, who deleted an item |

### 5.13 Accounting and the balance sheet (for owners and accountants)
- **Balance sheet:** what the shop owns, what it owes, and the owner's equity.
- **Income statement:** the real profit for the period.
- **Trial balance:** give it to your auditor (📤 Export or 🖨 Print). Double-click any account to see its statement.
- **Journal and account statement:** sales appear as one entry per day (clearer). Tick "Show every invoice" to see each invoice.
- **➕ Financial transaction:** capital, bank deposit, bank withdrawal, buying equipment, a loan and loan repayment, **offsetting input VAT and paying VAT due**, **depreciation of equipment and furniture**, and **bank fees**.
- **Manual entries** are for the accountant only, and an entry can be voided (it stays visible as voided).
- **Cash flow:** where cash came from and where it went (operations, assets, owner and loans); it always reconciles with the cash drawer, bank and wallets.
- **Fixed assets:** **+ Fixed asset** → name, cost, purchase date, useful life (furniture 5–10 years, devices 3–5, fridges 5–8) and how it was paid. **Depreciation is calculated monthly and posted automatically.** If the asset was already recorded with a "Buy equipment" transaction, choose "Already in the books". When you sell it: **💲 Sell/dispose** and the gain or loss is calculated for you.
- **Comparative income statement:** next to each line, **Previous period** and **Change %** columns (the previous period is chosen automatically: last month if you picked a month, last year if you picked a year).
- **Financial ratios:** 12 ratios as a financial analyst reads them, each with a colour and a plain explanation: gross and net margin, expense ratio, **liquidity** (can what you have pay what you owe?), **days stock stays on the shelf**, **days to collect debts** and **days to pay suppliers**, the **cash cycle**, the **break-even point** (how much you must sell monthly to cover expenses), **months of cash runway**, and return on equity. 🟢 good • 🟡 watch • 🔴 needs action.
- **Bank reconciliation (monthly):** enter the **bank statement** balance on a date → **⚖ Reconcile**. The program deducts amounts **in transit** (card and transfer sales from the last two days the bank hasn't settled yet) from the book balance and shows the difference. A small negative difference is usually bank fees: **🏦 Record the difference as bank fees and save** posts the entry automatically. Every reconciliation is kept in the history below, and the auditor reminds you if 45 days pass without one.
- **✅ Close month** (at the start of each month): choose the month → **🔎 Audit and close**. The program audits the whole month, opens the **closing pack** to print (income statement, balance sheet, cash flow, VAT return, trial balance, the auditor's opinion), then **locks the books** up to the end of the month: no entry or expense dated inside it can be added or deleted. If there are critical findings it asks before closing. To reopen the last closed month for a correction: **🔓 Reopen last closed month** (recorded in the activity log).
- **🖨 Printing never blocks your work:** printing any table in Accounting and Reports is prepared **in the background** with a slim progress bar at the bottom of the window ("Preparing the journal… page 40 of 296") while you keep selling or working. When it's done: **📄 Open** (in a PDF viewer), **🖨 Print** (choose the printer), **💾 Save as**, or **Cancel** while it's preparing. **The journal prints in full for the chosen period** (a whole year, about 300 pages, in seconds), with the shop header, logo and page numbers.
> Read "Accounting Made Simple" to understand the terms in plain language.

### 5.13.1 The financial audit (instead of an outside auditor)
🔎 **Financial audit** → choose the period (e.g. "This year" or "This month") → **▶ Start audit**.
- In two seconds the program checks every transaction and gives you an **opinion** (clean / qualified / adverse) and a **score** out of 100.
- **Findings are ordered by severity:** critical → high → medium → low. Click any finding to see the details, examples and the suggested action.
- Start with critical and high: for example a cash refund for an invoice paid by card, a transfer number used twice, or missing invoice numbers.
- **🖨 Audit report:** a formal report to print or save as PDF, for a partner, the bank or your auditor.
- **When?** It runs **by itself every day** in the background on the last 30 days, and a red "🔎 Daily auditor" button appears at the top if it finds something important. Run it manually after every stock count and before closing the year.
- **47 audit procedures**, including the most common retail fraud patterns:
  - **Sale then a cash refund within 30 minutes by the same cashier** (a real sale followed by a fake "return" to take the money).
  - **Sales outside the shop's usual hours.**
  - **A sudden jump in purchase cost** of more than 30% over the last purchase of the same item (compared per piece even when bought by the carton).
  - **Duplicate customers with the same phone number** (spreading debt across two accounts to get past the credit limit).
  - **Unusual payroll:** paid twice for the same month, for a month that hasn't started, or far above the approved salary.
  - **Bank reconciliation** that is old or has an unresolved difference, and **e-invoices** that are late or rejected.
  - Price changes at the till, rounding differences, and stale shelf labels.
- **Tamper seal:** every invoice and every line of the activity log is sealed with a chained digital fingerprint. If anyone edits or deletes an invoice directly in the data file (outside the program), it shows up as a critical finding with the invoice number.
> The audit sees everything recorded in the program, but not what was never recorded; physical stock counts and cash counts are still essential.

### 5.13.2 Shop assistant 🧭 (Max plan; zakat in Pro)
From the menu: **🧭 Shop assistant** — four tabs:

**💬 Ask your shop** — type your question the way you'd ask your accountant and press Enter:
- "How much did I sell today?" → sales compared with yesterday at the same hour, and the payment mix.
- "Profit last month?" • "Compare this month with last month" • "Electricity expenses this year?"
- "Who owes me money?" • "How much does Abu Sami owe?" • "Overdue debts" • "How much do we owe suppliers?"
- "How much sugar is left?" • "Price of oil?" • "What's running out?" • "Which items are not selling?"
- "Busiest hours?" • "My best customers" • "How much cash is in the drawer?" • "What is the shop worth?"
- "Forecast next month's sales" • "What should I prepare for Ramadan?" • "How much zakat?" • "Open inventory"
- It understands Arabic too, including everyday dialect.
- From any screen: type in the **✨ Ask your shop** box at the top or press **Ctrl+K**.

**🔮 Forecast & cash flow** — expected sales for the next 30 days, the weekly trend, expected cash day by day (with salaries, cheques and purchases), a warning if cash will run short, and items that will run out.
> Use it before agreeing a big payment with a supplier or buying new equipment: you'll know whether cash will be enough.

**🌙 Seasons & Ramadan** — choose the season (Ramadan, the two Eids, back to school, summer): the start date in Hijri and Gregorian, **order before**, expected sales, and for each item: how much you sold last season and how much it rose, plus the first order for the first 10 days. Order fresh goods in batches during the season.
> If the Hijri month starts a day earlier or later in your country, adjust "Hijri calendar correction" (hijri_adjust) in the settings.

**🕌 Zakat** — enter today's price of a gram of 24k gold, choose how to value stock (sale price or cost) and the type of year, then **Calculate zakat**: you get the zakat base in detail, the nisab, the zakat due, the next zakat date and a printable report.
> The calculation comes from the shop's books; if you have business cash outside the program or other debts due, enter them in their fields. For special cases, consult a scholar.

### 5.14 Daily summary on WhatsApp
Settings → Loyalty points & owner dashboard → "Owner's WhatsApp number". Then from the dashboard: **📱 Today's summary to owner** — a message with today's sales, profit, cash and alerts.

### 5.15 Several tills
1. On the main computer: Settings → This device & network → Network setup → "Main computer". Note the address and pairing code.
2. On each till: "Secondary point of sale" → the address and pairing code → 🔌 Test connection.
3. Restart the program on every computer. Each till has its own shift, drawer and printer.
4. The number of tills allowed depends on your plan.

### 5.15.1 Several branches (a chain)
Each branch runs its own copy, and the owner sees all branches in one report:
1. In each branch: Settings → Shop details → **"Branch name"**, and Settings → Backup → **"Second copy"** to a shared Google Drive folder.
2. On the owner's computer: Reports → **Branches** → **📁 Branch backups folder** → choose the same folder.
3. For each branch you see: invoices, net sales, gross profit, expenses, net profit, stock value, debts, and a **Total** row. Choose the period at the top.
- No internet in a branch? Send its backup file over WhatsApp or on a USB stick, and add it with **📥 Add branch file**.

### 5.15.2 Notes and reminders 📝
- The **📝** button at the top (or Ctrl+Shift+N): **+ New note** ← title and details ← **Remind me at** (date and time) ← repeat (daily, weekly, monthly, yearly) ← **💾 Save**.
- **Shared with all shop staff:** everyone who logs in sees it (like "count the fridge every week"). Notes that are not shared are visible only to you.
- When a reminder is due a small card appears at the bottom without stopping sales: **✓ Done** (a repeating reminder moves to its next date) or **⏰ In an hour**. The number of due reminders shows on the 📝 button.
- Ask your shop: "remind me" or "my notes" lists what is due and coming up.

### 5.16 Backup (never ignore it)
- An automatic copy every day and when the program closes.
- Settings → Backup → **Automatic second copy in a cloud folder**: choose a folder inside Google Drive or OneDrive. This is what saves you if the computer breaks or is stolen.
- Restore: "♻ Restore selected" (from the main computer only).
- **Updates:** when a new version is released a **⬆ New version — update** button appears at the top, or use ❓ Help ← **⬆ Updates**. Press **⬆ Update now**: the file is downloaded and verified, a backup is taken, then it installs and the program reopens within a minute. Finish any open sale first. Update every till the same way.

### 5.16.1 Appearance and logo
- **🌙 / ☀ at the top:** switches between dark and light mode instantly, on the same screen, without losing your cart or your work. In Settings → Shop details → **Appearance** you can also choose **Auto** to follow Windows. Each computer keeps its own look.
- **🌐 العربية / English:** switches the language instantly; a "Switching…" message appears, then the same screen opens in the other language with your cart as it was.
- **English item names:** in the English interface, item and category names are translated automatically ("حليب طازج 1 لتر" → Fresh Milk 1 L). To write a name yourself: edit the item → **English name**. To write names for all items at once for review: Inventory → **🌐 English names**. Search works with both names.
- **Shop logo:** Settings → Shop details → **🖼 Choose logo**. It appears at once in the sidebar, on the login screen and the customer display, on the receipt (black and white), A4 reports, statements, payslips, installment schedules, the audit and zakat reports, and in the owner dashboard and the online store. A square PNG with a transparent or white background works best.

### 5.17 Settings that suit your shop
| Setting | Where | What it does |
|---|---|---|
| **Simple mode** | Settings → Sales & inventory | Hides accounting, cheques, offers, reordering and the advisor. Untick it whenever you need them; no data is deleted |
| **Touch screen** | Settings → Sales & inventory | Bigger buttons and a number pad (this computer only, after a restart) |
| **Customer display** | Settings → Printing & cash drawer | A second screen showing the customer the items, total, savings and change |
| **Card terminal** | Settings → Printing & cash drawer | "Manual" without a connection (default), "Simulator" for training, "Terminal bridge" after your provider sets up the connection with your bank. Then "💳 Test connection" |
| **E-payments** | Settings → E-payments | The wallets and banking apps you accept (part 5.10) |
| **Tax invoice QR code** | Settings → Currency & tax | Enable it and enter your tax number; it prints on every receipt |
| **Connected e-invoicing** | Settings → E-invoicing | Link your invoices to the tax platform: Fatoora in Saudi Arabia or JoFotara in Jordan (part 5.18) |
| **Round every invoice up** | Settings → Sales & inventory | Makes the **⬆ Whole number** button active by default on every invoice |
| **Extra currencies** | Settings → Currency & tax | For example `USD=3.65,JOD=5.15`; a button appears for each currency in the payment window |
| **Language** | The **🌐 العربية / English** button at the top, or Settings → Shop details | The interface changes instantly without logging in again, stays on the same screen, and an open cart stays as it is |
| **Small screens** | Automatic | On laptops and small screens the menu folds into icons (hover over an icon to see its name), and the point of sale rearranges its buttons so they're always visible |

### 5.18 Connected e-invoicing with the tax platform (optional)
For shops registered in **Saudi Arabia** (Fatoora — phase 2, integration) or **Jordan** (the national invoicing system, JoFotara). Leave it off if you're not required to use it.

**What the program does:** every sales invoice and every return (credit note) becomes an **official UBL 2.1 e-invoice** at the moment of sale, and is sent to the platform **in the background** every minute. Selling **never stops**: if the internet is down, invoices wait in the queue and are sent when it's back.

**Saudi Arabia — Fatoora:**
1. Settings → **E-invoicing** → Platform: **Saudi Arabia**. Environment: start with the **developer sandbox**.
2. Fill in: legal name, commercial registration, national address (street, 4-digit building number, district, city, 5-digit postal code). The 15-digit VAT number comes from "Shop details"; enable 15% VAT in "Currency & tax". → **💾 Save settings**.
3. In the Fatoora portal (fatoora.zatca.gov.sa) → "Onboard new solution unit" → copy the **OTP** (the sandbox OTP is `123345`).
4. **🔗 Link this computer with Fatoora** → paste the code. The program generates the **signing key on this computer**, requests the certificate, passes ZATCA's **compliance checks** (invoice, credit note and debit note), then receives the **production certificate** — all in under a minute.
5. When the test succeeds: switch the environment to **Production**, save, and link again with an OTP from the production portal.
- Every invoice is **digitally signed** and chained: invoice counter (ICV) and previous invoice hash (PIH), so an invoice can't be removed from the middle without it showing.
- The receipt prints the **phase-2 QR code** (seller name, VAT number, time, total, VAT, hash, signature, public key and certificate signature) under the heading "Simplified tax invoice".
- **Rounding up** appears in the e-invoice as a payable rounding amount without touching VAT.

**Jordan — JoFotara:**
1. Register in the national invoicing system → "Link invoicing systems" → get the **Client ID**, **Secret Key** and **income source sequence number**.
2. Settings → E-invoicing → Platform: **Jordan** → enter them, choose the invoice type (general sales tax, or income only) → save.
3. On each sale the program sends the invoice right away before printing (up to 5 seconds) and prints **the QR code returned by the system** on the receipt. If the system is slow, the receipt prints without it, and the code appears when you reprint after it's sent.

**Monitoring:** the same tab shows ✅ reported, ⏳ waiting, ⛔ rejected. **📤 Send pending now** sends immediately, **📋 E-invoice log** shows every document with the platform's message, **💾 Save XML**, and **🔁 Resend** after fixing the reason for a rejection. The financial audit warns you if an invoice is more than **24 hours** late (the legal deadline in Saudi Arabia) or was rejected.
> **Secrets** (signing key, certificates, secret key) are stored inside the shop's data file and travel with the backup, and never appear on any screen or report.

---

<a id="6"></a>
## 6. Mobile: the app, owner dashboard and online store

### 6.1 The mobile app (Android)
1. On the shop's main computer, click the **📱 button at the top** (or Help → **📲 Link your phone**, or ask "how do I pair my phone?"). A window opens with two codes:
   - **Download code:** scan it with the phone camera to download the Android app. Install it; it asks for no permissions.
   - **Pairing code:** the shop computer's address on the network.
   If it shows "🔴 The phone service is off", click **▶ Start the phone service on this computer** (once; it keeps running on every start).
2. The first time, Windows Firewall may ask: choose **Allow**.
3. Open the app with the phone on the shop's Wi-Fi: it **finds the shop computer automatically** and opens directly. (If several shops are on the network it lists them; if none is found, tap **📷 Scan pairing QR** in the app and scan the "pairing code" from the window.)
4. Log in once with the same username and password as in the program — **you stay signed in**, even after the computer or phone restarts (until you sign out, change the password, or 90 days without use).
5. The app has tabs at the bottom; each employee sees what their permissions allow:
   | Tab | What's in it |
   |---|---|
   | 🏠 **Home** | Today's cards: sales, invoice count, profit, cash in the drawer, low-stock items, customer debts, open orders. Tap a card to go to its details |
   | 🔍 **Items** | The 📷 button scans any item's barcode: price, quantity, expiry and wholesale price (every plan). Staff with inventory permission type "Actual quantity on the shelf" → **Save count** |
   | 📦 **Low stock** | Items at their minimum, with a suggested order quantity. Tap one to see and count it |
   | 👥 **Customers** | Debtors from the highest debt down, search by name or phone, a **💬 WhatsApp reminder** with a ready message, and **📞 Call** |
   | 🛵 **Orders** | Open online orders with their items: **👨‍🍳 Preparing** → **✅ Ready** (opens WhatsApp with a message to the customer), or cancel. Converting to an invoice is done at the point of sale |
   | ✨ **Ask** | Ask your shop in your own words (Max plan) |
   Stock counts, low stock and customers are in Plus and above, orders come with the online store (Pro), and pages refresh by themselves every 30 seconds.
6. From the app menu (⋮): **Owner dashboard**, **Store**, or change shop.
7. If the computer's address changes (for example after the router restarts), the app finds it again automatically.
8. It follows the phone's dark/light mode automatically.

> **One time only:** if an old version of the app is on the phone and updating shows "App not installed", uninstall the old version and install the new one. Later updates install over it directly.

> **Security:** the default password (admin) does not work from the phone; change it in the program first. After 5 wrong sign-in attempts, signing in is locked for a short time.

> **iPhone:** open the address shown under "Owner dashboard" in the settings in Safari, then "Add to Home Screen".

### 6.2 Owner dashboard
Today's sales and profit, cash in the drawers, debts, alerts, and sales for the last 7 days — on your phone inside the shop.
**From outside the shop:** ask your provider to set up a secure connection (such as the free Tailscale) on the shop computer and your phone.

### 6.3 Online store and orders 🛵
1. Settings → **Online store** → enable the store, delivery, its fee and the minimum order.
2. The **🛵 Online orders** screen shows the store link: share it with customers (WhatsApp, a QR code on the shop door, Facebook).
3. When an order arrives, a number appears on the menu button with a sound alert:
   **👨‍🍳 Preparing** → **✅ Ready** → **📱 Notify customer** → on pickup **🧾 Convert to invoice**.
4. The delivery fee is added to the invoice as a "Delivery fee" line (a service with no stock), so it counts in sales and profit.

---

<a id="7"></a>
## 7. Hands-on exercises (on the training copy)

Do them in order. After each exercise, check the expected result.

| # | Exercise | Expected result |
|---|---|---|
| 1 | Log in as `cashier`, open a shift with 200, sell milk ×2 in cash and take 20 | The change appears and the receipt prints (or previews) |
| 2 | Scan `3*6223000000011` (tea biscuits) | The "buy 2 get 1 free" discount appears automatically |
| 3 | Scan `5449000000996` | "Cola (carton)" is added and 6 pieces are deducted from stock |
| 4 | Scan `7290000001028` (labneh) | A red warning: expired batch |
| 5 | Choose "Abu Ahmad" (F4) and sell on credit | His debt goes up in the customers screen |
| 6 | Give a 30% discount (F9) as cashier | Manager approval is requested (admin/admin) |
| 7 | In settings set the card terminal to "Simulator". In the payment window type cash 0.13 less than the total, then "💳 Pay by card on the terminal"; then set cash to 0 and try again | The first is declined with the bank's message (the simulator declines any amount ending in .13), the second is approved and its code prints on the receipt |
| 8 | Pay one invoice with **📲 PalPay** and type a transaction number, and another half in cash and half by "Instant bank transfer" | The method name and transaction number appear on the receipt |
| 9 | Return an item from an earlier invoice | It goes back to stock and the drawer goes down |
| 10 | Close the shift with 5 less than expected | "Shortage 5" appears in the shift report |
| 11 | As admin: a purchase invoice for two cartons of milk with an expiry date | Stock goes up by 24 and the batch appears in expiry |
| 12 | Return 4 labneh to "Al-Junaidi Company" | The supplier's account and stock go down |
| 13 | 🧠 Smart reordering → Calculate → choose a supplier → WhatsApp | A ready order message |
| 14 | 🏦 Cheques: click "Cleared" on Abu Khalil's cheque | It moves from "Cheques under collection" to "Bank" on the balance sheet |
| 15 | Open the balance sheet | ✓ Balanced: assets = liabilities + equity |
| 16 | 🤖 Smart advisor → read the first recommendation and click its link | You go to the right screen |
| 17 | Choose the customer "Neighborhood Grocery (wholesale)" in the point of sale and scan basmati rice | The price switches to the wholesale price |
| 18 | Customers → import credit book → save an empty template, add two customers with debts, and import it | The two customers appear with their debts |
| 19 | Turn "Simple mode" on, then off | Advanced screens disappear, then come back as before |
| 20 | Pair the mobile app by scanning the QR code and count an item | The quantity changes and the difference appears in item movements |
| 21 | Enable the store, order two items from a phone, then convert the order to an invoice | The order is "Completed" and linked to the invoice |
| 22 | Reports → E-payments → This month → choose PalPay | Its transactions with each transaction number, for reconciliation |
| 23 | Reports → Period summary → "Last 3 years" → Yearly, then Monthly | Sales growth year after year, and the Ramadan and summer peaks |
| 24 | Accounting → Financial transaction → "Transfer e-wallet balance to the bank" | The wallets balance goes down and the bank goes up on the balance sheet |
| 25 | 🧭 Shop assistant → Ask your shop: "profit last month", then "what should I prepare for Ramadan?" | The answer with figures, a comparison and a table; the Ramadan plan with order quantities |
| 26 | Click 🌙 at the top, then ☀ | The whole program switches to dark and back, on the same screen, in under a second |
| 27 | Sell two items whose total has decimals, and click **⬆ Whole number** before paying | The total becomes a whole number, a "Rounding" line prints, and the difference goes to "Invoice rounding differences" |
| 28 | Change an item's price, then return it from an old invoice | It's refunded at the old invoice price, and the item is in **🏷 Labels waiting to print** |
| 29 | Accounting → **Financial ratios**, then **Bank reconciliation** with a balance 5 lower | 12 ratios with their colours; the reconciliation shows a difference of 5 and offers to record it as bank fees |
| 30 | Employees & payroll → "Show former employees" → select Khaled → **🖨 Payslip** | A list of all his months, and the payslip for the one you pick |
| 31 | Reports → **Branches** | Hebron, Ramallah and Nablus with the total |
| 32 | On the phone: the **🛵 Orders** tab → "Ready" on an order | Its status changes in the program immediately and WhatsApp opens with the customer's message |

---

<a id="8"></a>
## 8. FAQ and troubleshooting

| Problem | Solution |
|---|---|
| The barcode isn't read | Make sure the cursor is in the search box (Esc brings it back). Try the scanner in Notepad: if nothing is typed, the problem is the scanner |
| "Not enough quantity in stock" | The item wasn't entered with a purchase invoice, or the count is wrong. Enter the quantity, or (carefully) enable "Allow selling when out of stock" |
| The printer doesn't print | Settings → Printing → choose the right printer and paper width → preview a test receipt. Make sure the printer is installed in Windows |
| The drawer doesn't open | Settings → Printing & cash drawer → connection type (usually through the printer) → "💰 Test drawer" |
| The customer says "I transferred" and it doesn't show in the shop's app | Don't hand over the goods. Ask them to open their app in front of you and show the transaction with your shop's name and its number |
| Card terminal "can't connect" | Settings → Printing & cash drawer → "💳 Test connection". If it continues: pay the manual way and contact your provider |
| Repeated cash shortages | Activity log: manual drawer openings, cash refunds, discounts; make sure withdrawals are recorded with "Cash withdrawal" |
| A secondary till "can't connect" | Is the main computer running? On the same network? Did the firewall allow the program? Has the main computer's address changed? |
| The mobile app "can't reach the shop computer" | Is the phone on the shop's Wi-Fi? Is the program running on the main computer? Tap "Retry" to search for it automatically, or scan the pairing code again |
| The phone says "Change the default password" | Sign in to the program on the computer and change the admin password, then use it on the phone |
| "Too many failed sign-in attempts" | Wait for the time shown (starting at 30 seconds), then enter the correct password |
| "Maximum number of licensed devices reached" | Your plan allows fewer tills; ask your provider to upgrade |
| A feature shows a 🔒 lock | It isn't in your current plan. Click **💎 Compare plans & upgrade** to see which plan includes it; your data and selling are not affected |
| "Activation key is for another device" | The key was issued for a different computer. Send your provider this device's code for a new key |
| "Invalid activation key format" | Copy the key **completely**, from `SA1.` to the last character, with nothing added or missing |
| Forgot the administrator password | Login screen → **"Forgot password?"** → send the device code to your provider on WhatsApp → type the code you receive and a new password. No data is deleted |
| Profit in "Reports" differs from what you expected | Check unrecorded expenses, damaged stock, and item costs (a zero cost inflates profit!) |
| The balance sheet shows a difference between physical and book inventory | Caused by selling with negative stock or editing costs manually. Count the items with negative quantities |
| "Owner's account" is a large number | Normal: it's the total the owner took from the drawers. It isn't a loss |
| Where is the phone pairing code? | The **📱** button at the top (on narrow screens: Help → **📲 Link your phone**) |
| An e-invoice is "Rejected" | Settings → E-invoicing → 📋 Log: read the platform's message (usually business details: VAT number or address), fix and save, then **🔁 Resend** |
| "Waiting for the device to be linked with Fatoora" | Linking isn't complete: 🔗 Link this computer with a new OTP. Invoices saved before linking are signed and sent automatically afterwards |
| The JoFotara QR code doesn't print | The system didn't respond within 5 seconds (internet). The invoice was sent later: reprint it from the invoice log and the code appears |
| The computer broke or was stolen | Install the program on a new computer, restore the latest copy from the Google Drive folder, then send the new device code to your provider to activate it |
