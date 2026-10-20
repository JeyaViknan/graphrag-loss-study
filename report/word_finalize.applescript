-- Opens a DOCX in Microsoft Word, refreshes every table of contents (twice, so
-- page numbers settle after the lists change length), saves it, and exports a PDF.
on run argv
	set inPath to item 1 of argv
	set pdfPath to item 2 of argv
	with timeout of 900 seconds
	tell application "Microsoft Word"
		open (POSIX file inPath)
		set d to active document
		repeat 2 times
			set n to count of tables of contents of d
			repeat with i from 1 to n
				update (table of contents i of d)
			end repeat
		end repeat
		save d
		save as d file name pdfPath file format format PDF
		close d saving no
	end tell
	end timeout
	return "ok"
end run
