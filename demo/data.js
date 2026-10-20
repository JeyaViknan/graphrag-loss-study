/* Corpus model for the X-Ray demo. Core entities and relationships follow the
   novel (George Eliot, Middlemarch, 1871-72). Long-tail entities, weights,
   token counts and every metric are generated in sim.js. */
var XR = window.XR = window.XR || {};

XR.CORPUS = { title: "Middlemarch", textUnits: 382, entities: 2184, relationships: 5906, budget: 8000 };

XR.LEVELS = [
  { name: "Leaf", long: "Leaf communities" },
  { name: "Community", long: "Communities" },
  { name: "Higher community", long: "Higher communities" },
  { name: "Root", long: "Root" }
];

/* L0 communities: [id, title, L1 parent, cx, cy, summary] */
XR.L0 = [
  [0, "Dorothea Brooke and Tipton Grange", "A", .12, .22, "Dorothea and Celia Brooke live at Tipton Grange with their uncle Arthur Brooke. Dorothea's cottage plans and her engagement to Casaubon are the most connected elements."],
  [1, "Casaubon and Lowick Manor", "B", .12, .64, "Edward Casaubon's estate and scholarship. The unfinished Key to All Mythologies and the codicil to his will dominate the community."],
  [2, "The wedding journey to Rome", "B", .22, .84, "The Casaubons' stay in Rome, where Dorothea meets Will Ladislaw and the painter Adolf Naumann."],
  [3, "Sir James Chettam and Freshitt Hall", "A", .25, .12, "Sir James Chettam, Lady Chettam and Freshitt Hall; Chettam's courtship of Dorothea and marriage to Celia."],
  [4, "The Cadwalladers of Tipton rectory", "A", .28, .31, "Mrs Cadwallader's matchmaking and the Rector's household link Tipton gossip to Freshitt and Lowick."],
  [5, "Mr Brooke's campaign and the Pioneer", "C", .37, .47, "Arthur Brooke's Reform candidacy, the Middlemarch Pioneer he buys, and Will Ladislaw's work as its editor."],
  [6, "The Vincy household", "D", .52, .31, "Walter Vincy, manufacturer and mayor, with Lucy Vincy and their children; the family's hospitality and spending."],
  [7, "Lydgate's marriage and debts", "D", .63, .20, "Tertius Lydgate's marriage to Rosamond Vincy, their household expenses and the debts that follow."],
  [8, "Middlemarch medical men", "E", .83, .12, "The established practitioners Sprague, Minchin, Wrench and Toller and their resistance to Lydgate's methods."],
  [9, "The New Fever Hospital", "E", .79, .30, "The fever hospital built with Bulstrode's money, its board of directors and the vote on the chaplaincy."],
  [10, "Farebrother and St Botolph's", "E", .93, .30, "Camden Farebrother, vicar of St Botolph's, with his mother, aunt and sister, and the whist that pays his way."],
  [11, "The Garth family", "F", .52, .61, "Caleb Garth, land agent, with Susan Garth and their children Mary and Alfred; the family's savings and work."],
  [12, "Fred Vincy's debts", "F", .63, .52, "Fred Vincy's horse dealing with Bambridge and Horrock, and the bill Caleb Garth signed for him."],
  [13, "Peter Featherstone and Stone Court", "G", .57, .85, "Old Featherstone's estate, his waiting relatives, his two wills and the funeral that brings Joshua Rigg to Stone Court."],
  [14, "Bulstrode's bank and charities", "H", .81, .56, "Nicholas Bulstrode, banker, his wife Harriet and his control of Middlemarch charities and loans."],
  [15, "Bulstrode's concealed past", "H", .93, .67, "Bulstrode's early career in a London business, his marriage to the widow Mrs Dunkirk and the daughter he kept hidden."],
  [16, "Raffles at Stone Court", "H", .78, .77, "John Raffles's return, his illness at Stone Court, the housekeeper Mrs Abel and his death."],
  [17, "Middlemarch town opinion", "H", .91, .87, "Hawley, Chichely and the talk at the Green Dragon; the public meeting at which Bulstrode is disgraced."],
  [18, "Lydgate's training in Paris", "D", .55, .08, "Lydgate's medical studies in Paris and his infatuation with the actress Laure."],
  [19, "Tipton estate tenants", "A", .07, .41, "Tenant farms on the Brooke estate, including Dagley's Freeman's End, and complaints about neglected cottages."],
  [20, "Auctions and trade", "C", .39, .63, "Borthrop Trumbull's auctions, the Larcher sale and the tradesmen who supply the town."],
  [21, "London and later practice", "D", .69, .07, "Lydgate's later practice in London and at a continental bathing-place, treating gout."]
];

XR.L1 = {
  A: ["Tipton and Freshitt society", "X", "Landed families of Tipton and Freshitt, their tenants and the rectory that connects them."],
  B: ["Lowick and the Casaubon marriage", "X", "Casaubon's household, scholarship and will, and the Roman wedding journey."],
  C: ["Reform politics and the Pioneer", "X", "Brooke's parliamentary campaign, the rival newspapers and the town's trade interests."],
  D: ["The Vincys and Lydgate", "Y", "The Vincy family, Rosamond's marriage to Lydgate, and Lydgate's career from Paris to London."],
  E: ["Medicine and the fever hospital", "Y", "Middlemarch doctors, the New Fever Hospital and the chaplaincy contest between Tyke and Farebrother."],
  F: ["Fred Vincy and the Garths", "Y", "Fred's debts, Caleb Garth's guarantee and the Garth household."],
  G: ["Featherstone's inheritance", "Y", "Stone Court, Featherstone's wills and the relatives who expected to inherit."],
  H: ["Bulstrode and the Raffles affair", "Z", "Bulstrode's bank, his hidden past, Raffles's death and the scandal that follows."]
};
XR.L2 = {
  X: ["The county: Tipton, Lowick and Reform", "Gentry households, Casaubon's estate and the Reform campaign."],
  Y: ["Middlemarch professions and families", "Doctors, manufacturers, land agents and the Featherstone inheritance."],
  Z: ["Bulstrode's downfall", "Bulstrode's finances, his concealed history and the public scandal."]
};
XR.ROOT = ["Middlemarch", "Provincial life in Middlemarch and its county between 1829 and 1832."];

/* Core entities: [name, type, L0 community, short label] */
XR.ENTITIES = [
  ["DOROTHEA BROOKE","PERSON",0,"DOROTHEA"],["CELIA BROOKE","PERSON",0,"CELIA"],["ARTHUR BROOKE","PERSON",0,"MR BROOKE"],["TIPTON GRANGE","PLACE",0],["TANTRIPP","PERSON",0],["MOTHER'S JEWELS","OBJECT",0],["COTTAGE PLANS","OBJECT",0],
  ["EDWARD CASAUBON","PERSON",1,"CASAUBON"],["LOWICK MANOR","PLACE",1,"LOWICK"],["KEY TO ALL MYTHOLOGIES","WORK",1],["CASAUBON'S CODICIL","DOCUMENT",1,"CODICIL"],["LOWICK CHURCH","PLACE",1],["MR TUCKER","PERSON",1],["AUNT JULIA'S MINIATURE","OBJECT",1],
  ["ROME","PLACE",2],["ADOLF NAUMANN","PERSON",2,"NAUMANN"],["VATICAN GALLERIES","PLACE",2],["WEDDING JOURNEY","EVENT",2],
  ["SIR JAMES CHETTAM","PERSON",3,"CHETTAM"],["LADY CHETTAM","PERSON",3],["FRESHITT HALL","PLACE",3],
  ["MRS CADWALLADER","PERSON",4],["HUMPHREY CADWALLADER","PERSON",4],["TIPTON RECTORY","PLACE",4],
  ["WILL LADISLAW","PERSON",5,"LADISLAW"],["MIDDLEMARCH PIONEER","ORGANIZATION",5,"THE PIONEER"],["REFORM BILL","EVENT",5],["NOMINATION MEETING","EVENT",5],["MR KECK","PERSON",5],["THE TRUMPET","ORGANIZATION",5],
  ["WALTER VINCY","PERSON",6,"MR VINCY"],["LUCY VINCY","PERSON",6,"MRS VINCY"],
  ["TERTIUS LYDGATE","PERSON",7,"LYDGATE"],["ROSAMOND VINCY","PERSON",7,"ROSAMOND"],["CAPTAIN LYDGATE","PERSON",7],["SIR GODWIN LYDGATE","PERSON",7],["MR DOVER","PERSON",7],["HOUSEHOLD DEBT","CONCEPT",7],["LOWICK GATE HOUSE","PLACE",7],
  ["DR SPRAGUE","PERSON",8],["DR MINCHIN","PERSON",8],["MR WRENCH","PERSON",8],["MR TOLLER","PERSON",8],
  ["NEW FEVER HOSPITAL","ORGANIZATION",9,"FEVER HOSPITAL"],["HOSPITAL BOARD","ORGANIZATION",9],["CHAPLAINCY ELECTION","EVENT",9,"CHAPLAINCY VOTE"],["WALTER TYKE","PERSON",9,"TYKE"],
  ["CAMDEN FAREBROTHER","PERSON",10,"FAREBROTHER"],["ST BOTOLPH'S","PLACE",10],["MISS NOBLE","PERSON",10],["MRS FAREBROTHER","PERSON",10],["WINIFRED FAREBROTHER","PERSON",10],
  ["CALEB GARTH","PERSON",11,"CALEB GARTH"],["SUSAN GARTH","PERSON",11,"SUSAN GARTH"],["MARY GARTH","PERSON",11,"MARY GARTH"],["ALFRED GARTH","PERSON",11],
  ["FRED VINCY","PERSON",12,"FRED VINCY"],["MR BAMBRIDGE","PERSON",12,"BAMBRIDGE"],["MR HORROCK","PERSON",12],["BILL OF DEBT","DOCUMENT",12,"FRED'S BILL"],["HOUNDSLEY HORSE FAIR","EVENT",12],["DIAMOND","ANIMAL",12],
  ["PETER FEATHERSTONE","PERSON",13,"FEATHERSTONE"],["STONE COURT","PLACE",13],["FEATHERSTONE'S WILL","DOCUMENT",13],["JOSHUA RIGG","PERSON",13,"RIGG"],["SOLOMON FEATHERSTONE","PERSON",13],["JANE WAULE","PERSON",13],["JONAH FEATHERSTONE","PERSON",13],["MR STANDISH","PERSON",13],["FEATHERSTONE'S FUNERAL","EVENT",13],
  ["NICHOLAS BULSTRODE","PERSON",14,"BULSTRODE"],["HARRIET BULSTRODE","PERSON",14],["MIDDLEMARCH BANK","ORGANIZATION",14],["£1,000 LOAN","CONCEPT",14],
  ["JOHN RAFFLES","PERSON",15,"RAFFLES"],["MRS DUNKIRK","PERSON",15,"MRS DUNKIRK"],["SARAH DUNKIRK","PERSON",15,"SARAH DUNKIRK"],["DUNKIRK PAWNBROKING BUSINESS","ORGANIZATION",15],
  ["MRS ABEL","PERSON",16],["OPIUM","OBJECT",16],["BRANDY","OBJECT",16],["RAFFLES'S DEATH","EVENT",16],
  ["MR HAWLEY","PERSON",17],["MR CHICHELY","PERSON",17],["NED PLYMDALE","PERSON",17],["MRS PLYMDALE","PERSON",17],["THE GREEN DRAGON","PLACE",17],["MIDDLEMARCH","PLACE",17],["SANITARY MEETING","EVENT",17],["BULSTRODE SCANDAL","EVENT",17],["CHOLERA","CONCEPT",17],
  ["PARIS","PLACE",18],["LAURE","PERSON",18],
  ["MR DAGLEY","PERSON",19],["FREEMAN'S END","PLACE",19],["TIPTON COTTAGES","PLACE",19],
  ["BORTHROP TRUMBULL","PERSON",20],["LARCHER SALE","EVENT",20],["MR MAWMSEY","PERSON",20],
  ["LONDON","PLACE",21],["BATHING-PLACE PRACTICE","ORGANIZATION",21]
];

/* Core relationships: [source, target, description label, weight] */
XR.RELS = [
  ["DOROTHEA BROOKE","CELIA BROOKE","sister of",8],["ARTHUR BROOKE","DOROTHEA BROOKE","uncle and guardian of",8],["ARTHUR BROOKE","TIPTON GRANGE","owns",6],
  ["DOROTHEA BROOKE","COTTAGE PLANS","draws up",5],["CELIA BROOKE","MOTHER'S JEWELS","takes most of",3],["TANTRIPP","DOROTHEA BROOKE","maid to",4],["DOROTHEA BROOKE","TIPTON GRANGE","lives at",5],
  ["DOROTHEA BROOKE","EDWARD CASAUBON","marries",9],["EDWARD CASAUBON","LOWICK MANOR","owns",7],["EDWARD CASAUBON","KEY TO ALL MYTHOLOGIES","writes",8],
  ["EDWARD CASAUBON","CASAUBON'S CODICIL","adds",6],["CASAUBON'S CODICIL","WILL LADISLAW","revokes inheritance if Dorothea marries",4],
  ["EDWARD CASAUBON","LOWICK CHURCH","rector of",4],["MR TUCKER","EDWARD CASAUBON","curate to",3],["AUNT JULIA'S MINIATURE","LOWICK MANOR","hangs in",2],
  ["WILL LADISLAW","AUNT JULIA'S MINIATURE","resembles",2],["EDWARD CASAUBON","WILL LADISLAW","cousin of",6],
  ["DOROTHEA BROOKE","LOWICK MANOR","gives up",5],["DOROTHEA BROOKE","WILL LADISLAW","marries",7],
  ["DOROTHEA BROOKE","ROME","travels to",5],["EDWARD CASAUBON","VATICAN GALLERIES","researches at",3],["WILL LADISLAW","ADOLF NAUMANN","studies painting with",5],
  ["ADOLF NAUMANN","DOROTHEA BROOKE","sketches",3],["WEDDING JOURNEY","ROME","takes place in",4],["EDWARD CASAUBON","WEDDING JOURNEY","takes",3],
  ["SIR JAMES CHETTAM","FRESHITT HALL","owns",5],["LADY CHETTAM","SIR JAMES CHETTAM","mother of",4],["SIR JAMES CHETTAM","CELIA BROOKE","marries",7],
  ["SIR JAMES CHETTAM","DOROTHEA BROOKE","courts",4],["SIR JAMES CHETTAM","COTTAGE PLANS","builds cottages from",4],["SIR JAMES CHETTAM","WILL LADISLAW","opposes",3],
  ["MRS CADWALLADER","HUMPHREY CADWALLADER","wife of",6],["HUMPHREY CADWALLADER","TIPTON RECTORY","rector of",4],["MRS CADWALLADER","SIR JAMES CHETTAM","promotes match for",3],
  ["MRS CADWALLADER","ARTHUR BROOKE","gossips about",3],["HUMPHREY CADWALLADER","SIR JAMES CHETTAM","advises",2],
  ["ARTHUR BROOKE","MIDDLEMARCH PIONEER","buys",6],["WILL LADISLAW","MIDDLEMARCH PIONEER","edits",7],["ARTHUR BROOKE","REFORM BILL","stands for Parliament on",5],
  ["ARTHUR BROOKE","NOMINATION MEETING","speaks at",5],["MR KECK","THE TRUMPET","edits",5],["THE TRUMPET","ARTHUR BROOKE","attacks",3],
  ["WILL LADISLAW","ARTHUR BROOKE","writes speeches for",4],["MIDDLEMARCH PIONEER","REFORM BILL","supports",4],
  ["MR DAGLEY","FREEMAN'S END","farms",5],["MR DAGLEY","ARTHUR BROOKE","confronts",4],["FREEMAN'S END","TIPTON GRANGE","on the estate of",3],["THE TRUMPET","FREEMAN'S END","reports on",2],["ARTHUR BROOKE","TIPTON COTTAGES","neglects",3],
  ["BORTHROP TRUMBULL","LARCHER SALE","auctions",5],["BORTHROP TRUMBULL","PETER FEATHERSTONE","cousin of",3],["ARTHUR BROOKE","MR MAWMSEY","canvasses",3],
  ["WALTER VINCY","LUCY VINCY","husband of",6],["WALTER VINCY","ROSAMOND VINCY","father of",7],["WALTER VINCY","FRED VINCY","father of",7],
  ["LUCY VINCY","ROSAMOND VINCY","mother of",5],["WALTER VINCY","MIDDLEMARCH","mayor of",4],["HARRIET BULSTRODE","WALTER VINCY","sister of",6],["LUCY VINCY","FRED VINCY","nurses",3],
  ["TERTIUS LYDGATE","ROSAMOND VINCY","marries",9],["TERTIUS LYDGATE","MR DOVER","owes",4],["TERTIUS LYDGATE","HOUSEHOLD DEBT","incurs",6],
  ["ROSAMOND VINCY","SIR GODWIN LYDGATE","writes for money to",4],["CAPTAIN LYDGATE","ROSAMOND VINCY","rides out with",4],["TERTIUS LYDGATE","SIR GODWIN LYDGATE","nephew of",5],
  ["TERTIUS LYDGATE","LOWICK GATE HOUSE","rents",3],["ROSAMOND VINCY","TERTIUS LYDGATE","urges to leave Middlemarch",3],["TERTIUS LYDGATE","MIDDLEMARCH","leaves",4],
  ["TERTIUS LYDGATE","PARIS","studies medicine in",5],["LAURE","PARIS","actress in",4],["TERTIUS LYDGATE","LAURE","infatuated with",4],
  ["TERTIUS LYDGATE","LONDON","later practises in",3],["TERTIUS LYDGATE","BATHING-PLACE PRACTICE","treats gout at",2],["ROSAMOND VINCY","LONDON","prefers",2],
  ["DR SPRAGUE","TERTIUS LYDGATE","rival of",4],["DR MINCHIN","TERTIUS LYDGATE","rival of",3],["MR WRENCH","FRED VINCY","attends",4],
  ["TERTIUS LYDGATE","FRED VINCY","diagnoses typhoid in",5],["MR TOLLER","TERTIUS LYDGATE","ridicules",2],["DR SPRAGUE","DR MINCHIN","colleague of",4],["MR WRENCH","TERTIUS LYDGATE","resents",3],
  ["NICHOLAS BULSTRODE","NEW FEVER HOSPITAL","funds",7],["TERTIUS LYDGATE","NEW FEVER HOSPITAL","directs medicine at",6],["HOSPITAL BOARD","CHAPLAINCY ELECTION","holds",5],
  ["NICHOLAS BULSTRODE","WALTER TYKE","supports",5],["TERTIUS LYDGATE","WALTER TYKE","votes for",4],["CAMDEN FAREBROTHER","CHAPLAINCY ELECTION","candidate in",4],
  ["WALTER TYKE","CHAPLAINCY ELECTION","wins",5],["DR SPRAGUE","NEW FEVER HOSPITAL","refuses to support",3],["DOROTHEA BROOKE","NEW FEVER HOSPITAL","offers to fund",3],
  ["CAMDEN FAREBROTHER","ST BOTOLPH'S","vicar of",6],["MRS FAREBROTHER","CAMDEN FAREBROTHER","mother of",5],["MISS NOBLE","CAMDEN FAREBROTHER","aunt of",4],
  ["WINIFRED FAREBROTHER","CAMDEN FAREBROTHER","sister of",4],["CAMDEN FAREBROTHER","TERTIUS LYDGATE","friend of",5],["CAMDEN FAREBROTHER","MARY GARTH","loves",4],
  ["CAMDEN FAREBROTHER","DOROTHEA BROOKE","receives Lowick living from",4],["CAMDEN FAREBROTHER","FRED VINCY","advises",4],
  ["CALEB GARTH","SUSAN GARTH","husband of",7],["CALEB GARTH","MARY GARTH","father of",7],["SUSAN GARTH","ALFRED GARTH","mother of",4],
  ["CALEB GARTH","FRED VINCY","co-signs bill for",6],["SUSAN GARTH","BILL OF DEBT","pays Alfred's £92 toward",3],["MARY GARTH","BILL OF DEBT","gives her £18 toward",2],
  ["FRED VINCY","MARY GARTH","loves",8],["CALEB GARTH","ARTHUR BROOKE","land agent for",3],["CALEB GARTH","SIR JAMES CHETTAM","land agent for",3],["MARY GARTH","PETER FEATHERSTONE","nurses",6],
  ["FRED VINCY","MR BAMBRIDGE","owes money to",4],["FRED VINCY","MR HORROCK","trades horses with",3],["FRED VINCY","DIAMOND","buys",3],["FRED VINCY","HOUNDSLEY HORSE FAIR","attends",3],
  ["BILL OF DEBT","FRED VINCY","signed for",5],["MR BAMBRIDGE","HOUNDSLEY HORSE FAIR","sells horses at",3],
  ["PETER FEATHERSTONE","STONE COURT","owns",7],["PETER FEATHERSTONE","FEATHERSTONE'S WILL","writes",6],["FEATHERSTONE'S WILL","JOSHUA RIGG","leaves Stone Court to",5],
  ["SOLOMON FEATHERSTONE","PETER FEATHERSTONE","brother of",4],["JANE WAULE","PETER FEATHERSTONE","sister of",4],["JONAH FEATHERSTONE","PETER FEATHERSTONE","brother of",3],
  ["MR STANDISH","FEATHERSTONE'S WILL","reads",4],["PETER FEATHERSTONE","FRED VINCY","uncle of",4],["FEATHERSTONE'S FUNERAL","STONE COURT","held at",3],
  ["JOSHUA RIGG","NICHOLAS BULSTRODE","sells Stone Court to",5],["JOHN RAFFLES","JOSHUA RIGG","stepfather of",4],["MARY GARTH","FEATHERSTONE'S WILL","refuses to burn",4],
  ["NICHOLAS BULSTRODE","HARRIET BULSTRODE","husband of",7],["NICHOLAS BULSTRODE","MIDDLEMARCH BANK","owns",6],["NICHOLAS BULSTRODE","£1,000 LOAN","makes",5],
  ["NICHOLAS BULSTRODE","TERTIUS LYDGATE","lends £1,000 to",4],["£1,000 LOAN","HOUSEHOLD DEBT","clears",4],["HARRIET BULSTRODE","ROSAMOND VINCY","aunt of",4],
  ["NICHOLAS BULSTRODE","STONE COURT","buys",5],["DOROTHEA BROOKE","TERTIUS LYDGATE","repays the £1,000 for",3],
  ["NICHOLAS BULSTRODE","MRS DUNKIRK","married",4],["SARAH DUNKIRK","MRS DUNKIRK","daughter of",5],["SARAH DUNKIRK","WILL LADISLAW","mother of",2],
  ["JOHN RAFFLES","SARAH DUNKIRK","finds and conceals",3],["NICHOLAS BULSTRODE","DUNKIRK PAWNBROKING BUSINESS","managed",4],["JOHN RAFFLES","NICHOLAS BULSTRODE","blackmails",6],
  ["JOHN RAFFLES","WILL LADISLAW","reveals parentage to",3],["NICHOLAS BULSTRODE","WILL LADISLAW","offers money to",3],
  ["JOHN RAFFLES","TERTIUS LYDGATE","dies under the care of",4],["MRS ABEL","JOHN RAFFLES","gives brandy to",4],["NICHOLAS BULSTRODE","MRS ABEL","hands the brandy key to",3],
  ["TERTIUS LYDGATE","OPIUM","limits the dose of",3],["RAFFLES'S DEATH","STONE COURT","occurs at",4],["JOHN RAFFLES","RAFFLES'S DEATH","subject of",5],
  ["BRANDY","RAFFLES'S DEATH","contributes to",3],["OPIUM","RAFFLES'S DEATH","contributes to",3],
  ["MR HAWLEY","BULSTRODE SCANDAL","exposes",5],["BULSTRODE SCANDAL","NICHOLAS BULSTRODE","disgraces",6],["BULSTRODE SCANDAL","TERTIUS LYDGATE","implicates",5],
  ["SANITARY MEETING","BULSTRODE SCANDAL","site of",4],["MR CHICHELY","SANITARY MEETING","attends",3],["MR BAMBRIDGE","THE GREEN DRAGON","repeats Raffles's story at",3],
  ["NED PLYMDALE","MRS PLYMDALE","son of",4],["NED PLYMDALE","ROSAMOND VINCY","courts",3],["MRS PLYMDALE","HARRIET BULSTRODE","friend of",4],
  ["CHOLERA","SANITARY MEETING","prompts",3],["TERTIUS LYDGATE","SANITARY MEETING","attends",3],
  ["MR HAWLEY","MIDDLEMARCH","lawyer in",3],["THE GREEN DRAGON","MIDDLEMARCH","inn in",3]
];

/* Featured queries. hops reference RELS by [source, target]. */
XR.QUERIES = [
  { id: "Q-017", label: "Lydgate leaves Middlemarch", type: "Complex reasoning",
    text: "Who influenced Tertius Lydgate's decision to leave Middlemarch?",
    gold: "Rosamond, and the Bulstrode–Raffles scandal",
    hops: [["JOHN RAFFLES","NICHOLAS BULSTRODE"],["NICHOLAS BULSTRODE","TERTIUS LYDGATE"],["JOHN RAFFLES","TERTIUS LYDGATE"],["ROSAMOND VINCY","TERTIUS LYDGATE","urges to leave Middlemarch"],["TERTIUS LYDGATE","MIDDLEMARCH"]],
    answers: {
      correct: "Rosamond pressed him to leave, and his standing collapsed when Raffles died in his care soon after Bulstrode lent him £1,000 — the town read the loan as a bribe.",
      partial: "Lydgate left once his practice declined and Rosamond wanted to move; the context does not explain what damaged his reputation.",
      incorrect: "The summaries attribute Lydgate's departure to household debt. No person is identified as influencing the decision."
    } },
  { id: "Q-004", label: "Dorothea gives up Lowick", type: "Complex reasoning",
    text: "Why did Dorothea give up the Lowick estate?",
    gold: "Casaubon's codicil disinherited her if she married Will Ladislaw",
    hops: [["EDWARD CASAUBON","CASAUBON'S CODICIL"],["CASAUBON'S CODICIL","WILL LADISLAW"],["DOROTHEA BROOKE","WILL LADISLAW"],["DOROTHEA BROOKE","LOWICK MANOR"]],
    answers: {
      correct: "Casaubon's codicil revoked her inheritance if she married Will Ladislaw. She married Will, and so gave up Lowick.",
      partial: "Dorothea left Lowick after Casaubon's death; the summaries mention a codicil but not what it required.",
      incorrect: "The summaries describe Dorothea as Casaubon's heir to Lowick and do not say she gave the estate up."
    } },
  { id: "Q-031", label: "Fred Vincy's unpaid bill", type: "Fact retrieval",
    text: "Whose savings were lost when Fred Vincy could not repay his debt?",
    gold: "The Garths — Susan's £92 for Alfred and Mary's £18",
    hops: [["FRED VINCY","MR BAMBRIDGE"],["CALEB GARTH","FRED VINCY"],["SUSAN GARTH","BILL OF DEBT"],["MARY GARTH","BILL OF DEBT"]],
    answers: {
      correct: "The Garths. Caleb had co-signed Fred's bill, so Susan Garth paid in the £92 saved for Alfred's apprenticeship and Mary gave her £18.",
      partial: "Caleb Garth had signed Fred's bill and his family covered it; the context does not say whose savings were used.",
      incorrect: "The summaries say Fred owed money to Bambridge. They do not identify anyone else who lost money."
    } },
  { id: "Q-022", label: "The chaplaincy vote", type: "Complex reasoning",
    text: "Why did Lydgate vote for Tyke rather than Farebrother as hospital chaplain?",
    gold: "He depended on Bulstrode, who funded the hospital and backed Tyke",
    hops: [["NICHOLAS BULSTRODE","NEW FEVER HOSPITAL"],["NICHOLAS BULSTRODE","WALTER TYKE"],["TERTIUS LYDGATE","WALTER TYKE"],["CAMDEN FAREBROTHER","CHAPLAINCY ELECTION"]],
    answers: {
      correct: "Lydgate needed Bulstrode's backing to run the New Fever Hospital, and Bulstrode supported Tyke — so Lydgate voted against his friend Farebrother.",
      partial: "Tyke won with the hospital board's support and Lydgate voted for him; the reason is not in the retrieved context.",
      incorrect: "The summaries describe a chaplaincy election won by Tyke. Lydgate's vote is not mentioned."
    } },
  { id: "Q-040", label: "Bulstrode's fortune", type: "Complex reasoning",
    text: "How is Will Ladislaw connected to Bulstrode's fortune?",
    gold: "Will's mother Sarah was the disowned daughter of Bulstrode's first wife",
    hops: [["NICHOLAS BULSTRODE","MRS DUNKIRK"],["SARAH DUNKIRK","MRS DUNKIRK"],["SARAH DUNKIRK","WILL LADISLAW"],["JOHN RAFFLES","SARAH DUNKIRK"]],
    answers: {
      correct: "Bulstrode's fortune came from marrying the widow Mrs Dunkirk. Her estranged daughter Sarah — found by Raffles and kept hidden by Bulstrode — was Will Ladislaw's mother.",
      partial: "Bulstrode's wealth came from his marriage to Mrs Dunkirk, whose daughter he concealed; the link to Will is not in the context.",
      incorrect: "The summaries describe Bulstrode as a banker and do not connect his fortune to Will Ladislaw."
    } }
];

/* Name pools for long-tail entities extracted from minor passages. */
XR.POOL = {
  surnames: ["Pinkerton","Bowyer","Hackbutt","Powderell","Limp","Crabbe","Dill","Spilkins","Dollop","Gambit","Brindley","Hopkins","Baldwin","Tolley","Fitchett","Kimble","Brewitt","Lathrop","Arbury","Goby","Wimple","Codling","Sprott","Marsden","Ladbrook","Pegwell","Horsley","Filmore","Carter","Hackett","Bunney","Taft","Jonas","Tiller","Mottram","Crowse","Larcher","Toller","Vigo","Blinkhorn","Pratt","Hicks","Ashby","Farley","Gilroy","Marsh","Penfold","Quallon","Rodley","Stubbs","Thorne","Upcott","Wakefield","Yelland"],
  titles: ["MR","MRS","MISS","FARMER","OLD","YOUNG"],
  places: ["THE TANKARD","SLAUGHTER LANE","BRASSING","BILKLEY","YODDRELL'S FARM","HALSELL COMMON","BRIDGE STREET","TIPTON MILL","LOWICK PARISH SCHOOL","THE WHITE HART","CHURCH LANE","FRESHITT PARK","THE RAILWAY SURVEY","FRICK","MIDDLEMARCH MARKET","PAUL'S WHARF","THE COUNTY GAOL","ST PETER'S","GREEN LANE","RIVERSTON"],
  things: ["TITHES","POOR RATES","GLEBE LAND","FEVER WARD","DISPENSARY","STETHOSCOPE","CHAPEL SUBSCRIPTION","TURNPIKE TRUST","COMMUNION PLATE","PARISH VESTRY","MORTGAGE","RENT ROLL","DRAINAGE SCHEME","BURIAL GROUND","CANVASS","LEASE","MARRIAGE SETTLEMENT","GAMING DEBT","HORSE-DEALING","WHIST TABLE"],
  rels: ["tenant of","patient of","creditor of","neighbour of","works for","servant at","relative of","witness to","supplies","gossips about","votes against","subscribes to","lodges at","sells to","borrows from","attends","visits","complains to","trades with","owes rent to"]
};
