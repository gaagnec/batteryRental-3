# Calculate sizes
admin_phoenix = 16662 / 1024  # 16.27 KB
bootstrap_icons = 98255 / 1024  # 95.95 KB
bootstrap_css = 232803 / 1024  # 227.35 KB
bootstrap_js = 80721 / 1024  # 78.83 KB

total_static = admin_phoenix + bootstrap_icons + bootstrap_css + bootstrap_js

print("=== OPTIMIZATION RESULTS ===")
print()
print("Static Files Created:")
print(f"  admin-phoenix.css:       {admin_phoenix:.2f} KB")
print(f"  bootstrap-icons.css:     {bootstrap_icons:.2f} KB")
print(f"  bootstrap.min.css:       {bootstrap_css:.2f} KB")
print(f"  bootstrap.bundle.min.js: {bootstrap_js:.2f} KB")
print(f"  TOTAL:                   {total_static:.2f} KB")
print()
print("Comparison:")
print(f"  BEFORE (CDN + Inline):   428.12 KB (402KB CDN + 25.7KB inline + small HTML)")
print(f"  AFTER (Local files):     {total_static:.2f} KB")
print()
print("Expected with gzip (70% compression):")
print(f"  Page size compressed:    ~{total_static * 0.3:.2f} KB")
print()
print("Benefits:")
print("  - All files cached by browser")
print("  - No external CDN requests")
print("  - Faster load time (same domain)")
print("  - Gzip compression enabled")

