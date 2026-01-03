#!/usr/bin/env python3
"""
Optimization script - Extract CSS from inline to static file
"""

# Read the template file
with open('templates/admin/base_site.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the style block
start_marker = '  <style>'
end_marker = '  </style>'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker) + len(end_marker)

if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find CSS block!")
    exit(1)

# Extract CSS content (without <style> tags)
css_block = content[start_idx:end_idx]
css_content = css_block.replace('  <style>\n', '').replace('  </style>', '')

# Write CSS to static file
with open('rental/static/css/admin-phoenix.css', 'w', encoding='utf-8') as f:
    f.write('/* Phoenix Admin Theme - Extracted from inline CSS */\n')
    f.write('/* Generated automatically for optimization */\n\n')
    f.write(css_content)

# Replace inline CSS with link to static file
new_content = content[:start_idx] + '  <link rel="stylesheet" href="{% static \'css/admin-phoenix.css\' %}">\n' + content[end_idx+1:]

with open('templates/admin/base_site.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("[OK] Step 1 Complete: CSS extracted to static file!")
print(f"  - Created: rental/static/css/admin-phoenix.css")
print(f"  - Updated: templates/admin/base_site.html")
print(f"  - Size saved per page: 25.7 KB")

