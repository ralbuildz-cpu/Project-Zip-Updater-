project_update_from_zip.py
I built this because I kept getting zip files back from AI edits and needed a safe way to merge them into an existing project without overwriting everything by hand.

It compares a zip against your current project folder, shows you what is new or different, and lets you pick which files to actually update.

What it does
Opens a file picker starting in Downloads so you can find the zip
Extracts the zip to a temp folder and compares each file to your live project using SHA-256
Strips a common top-level folder if the zip has one (like myproject-v2/)
Lists files as [NEW] or [MODIFIED]
Lets you scroll with arrow keys and toggle files with Space, then hit Enter to confirm
Backs up any file you overwrite as filename.ext.bak before copying
Skips itself, .gitignore, and anything inside .git
Cleans up the temp files when done
If it finds version_manager.py in the same folder, it offers to run it so you can commit the changes
When to use it
Run this from the root of the project you want to update. Typical flow for me:

AI generates or edits a multi-file app
I download the updated files as a zip
I run this script in my live project folder
I pick only the files I want to bring in
How to run
Requirements: Python 3.7 or newer. No extra packages.

Copy project_update_from_zip.py into your project root
Open a terminal in that folder
Run:
Code
python project_update_from_zip.py
On Windows use python or py, on Mac/Linux use python3.

Use the arrow keys to move, Space to select, Enter to confirm. Press q to back out.

After updating
It will tell you how many .bak files were made and ask if you want to delete them
If you keep them, you can delete them later manually
If version_manager.py exists, you get a prompt to launch it
Notes
The script assumes the folder it lives in is your live project root (LIVE_ROOT = SCRIPT_PATH.parent)
It works on Windows and Linux/Mac terminals
It does not delete files that are in your live project but missing from the zip, it only shows a count
Large binary files work fine, it just compares hashes
That's it. Copy, run, pick, done.

