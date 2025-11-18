#!/usr/bin/env python3
"""
Algorithm to extract and organize comic data into hierarchical structure:
- series_name
  issue 1
    Hindi Variant
    English Variant
    Special Variant
  issue 2
    ...
- combo
  series_1
    issue1, issue2, etc.
"""

import json
import re
from typing import Dict, List, Any, Optional
from collections import defaultdict
import unicodedata


def is_combo_item(item: Dict[str, Any]) -> bool:
    """Check if an item is a combo/bundle."""
    title = item.get('title', '').lower()
    combo_keywords = [
        'combo', 'all variants', 'bundle', 'set', 'pack',
        'combo of', 'all variant', 'variants combo'
    ]
    return any(keyword in title for keyword in combo_keywords)


def is_publisher_item(item: Dict[str, Any]) -> bool:
    """Check if an item is a publisher info item."""
    return 'name' in item and 'title' not in item


def extract_variant_info(item: Dict[str, Any]) -> str:
    """
    Extract variant information from title.
    Returns a string describing the variant (e.g., "Hindi Variant", "English Regular Cover")
    """
    title = item.get('title', '')
    language = item.get('language', '')
    cover_artist = item.get('cover_artist', '')
    binding = item.get('binding', '')
    
    variant_parts = []
    
    # Add language
    if language:
        variant_parts.append(language)
    
    # Extract variant type from title
    title_lower = title.lower()
    
    # Check for variant keywords
    variant_types = []
    if 'variant' in title_lower:
        # Extract variant description
        variant_match = re.search(r'variant\s+(?:cover\s+)?(?:by\s+)?([^–-]+)', title, re.IGNORECASE)
        if variant_match:
            variant_desc = variant_match.group(1).strip()
            # Clean up common suffixes
            variant_desc = re.sub(r'\s*(cover|by|variant).*$', '', variant_desc, flags=re.IGNORECASE).strip()
            if variant_desc and len(variant_desc) < 50:  # Reasonable length
                variant_types.append(variant_desc)
        else:
            variant_types.append('Variant')
    elif 'regular' in title_lower or 'default' in title_lower:
        variant_types.append('Regular')
    elif 'blank' in title_lower:
        variant_types.append('Blank')
    elif 'homage' in title_lower:
        variant_types.append('Homage')
    elif 'wraparound' in title_lower:
        variant_types.append('Wraparound')
    elif 'hand painted' in title_lower or 'hand-painted' in title_lower:
        variant_types.append('Hand Painted')
    elif 'sketch' in title_lower:
        variant_types.append('Sketch')
    elif 'directors cut' in title_lower or "director's cut" in title_lower:
        variant_types.append("Director's Cut")
    elif 'action figure' in title_lower:
        variant_types.append('Action Figure')
    elif 'poster' in title_lower:
        variant_types.append('Poster')
    
    # Add cover artist if available and not already in variant
    if cover_artist and cover_artist not in ' '.join(variant_types):
        variant_types.append(f"by {cover_artist}")
    
    # Add binding if it's not standard paperback
    if binding and binding.lower() not in ['paperback', '']:
        variant_types.append(binding)
    
    # Combine all parts
    if variant_types:
        variant_parts.extend(variant_types)
    
    # If no variant info found, use language or "Standard"
    if not variant_parts:
        if language:
            variant_parts.append(language)
        else:
            variant_parts.append('Standard')
    
    return ' '.join(variant_parts).strip()


def normalize_series_name(series_name: str) -> str:
    """
    Normalize series names to merge variations.
    For example: "Yagyaa Origins" → "Yagyaa" (since it's Issue 5 of Yagyaa)
    
    Rules:
    - "Series Name Origins" → "Series Name"
    - "Series Name: Subtitle" → "Series Name"
    - "Series Name - Subtitle" → "Series Name"
    - Strip common suffixes that indicate it's part of the main series
    """
    if not series_name:
        return series_name
    
    # Common patterns that indicate a sub-series is actually part of the main series
    # Pattern: "Series Name Origins" → "Series Name"
    origins_match = re.search(r'^(.+?)\s+Origins\s*$', series_name, re.IGNORECASE)
    if origins_match:
        base_name = origins_match.group(1).strip()
        # Only merge if base name exists and is not too short
        if base_name and len(base_name) > 2:
            return base_name
    
    # Pattern: "Series Name: Subtitle" → "Series Name"
    colon_match = re.search(r'^([^:]+?)(?:\s*:\s*.+)?$', series_name)
    if colon_match:
        base_name = colon_match.group(1).strip()
        if base_name and len(base_name) > 2:
            # Check if it's a meaningful split (not just removing a colon at the end)
            if ':' in series_name and base_name != series_name:
                return base_name
    
    # Pattern: "Series Name - Subtitle" → "Series Name"
    dash_match = re.search(r'^([^–\-]+?)(?:\s*[–\-]\s*.+)?$', series_name)
    if dash_match:
        base_name = dash_match.group(1).strip()
        if base_name and len(base_name) > 2:
            # Check if it's a meaningful split
            if ('–' in series_name or '-' in series_name) and base_name != series_name:
                return base_name
    
    # Return original if no normalization needed
    return series_name


def extract_combo_issues(combo_item: Dict[str, Any]) -> List[int]:
    """
    Extract issue numbers from combo item title.
    Returns list of issue numbers mentioned in the combo.
    """
    title = combo_item.get('title', '')
    issue = combo_item.get('issue')
    
    issues = []
    
    # Extract issue ranges from title (e.g., "Issue 1-5", "Issue 1, 2, 3")
    # Pattern: Issue 1-5 or Issue 1, 2, 3 or Issue 1,2,3
    issue_range_pattern = r'issue\s+(\d+)(?:\s*[-–]\s*(\d+))?'
    issue_list_pattern = r'issue\s+(\d+(?:\s*[,&]\s*\d+)+)'
    
    # Try range pattern first (e.g., "Issue 1-5", "Issue 1–5")
    range_match = re.search(issue_range_pattern, title, re.IGNORECASE)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2)) if range_match.group(2) else start
        issues.extend(range(start, end + 1))
    
    # Try list pattern (e.g., "Issue 1, 2, 3" or "Issue 1,2,3")
    if not issues:
        list_match = re.search(issue_list_pattern, title, re.IGNORECASE)
        if list_match:
            issue_str = list_match.group(1)
            issue_nums = re.findall(r'\d+', issue_str)
            issues.extend([int(n) for n in issue_nums])
    
    # Extract standalone issue numbers (e.g., "Issue 1", "Issue 2")
    if not issues:
        standalone_issues = re.findall(r'\bissue\s+(\d+)\b', title, re.IGNORECASE)
        issues.extend([int(n) for n in standalone_issues])
    
    # Extract "Book 1", "Book 2" patterns
    if not issues:
        book_issues = re.findall(r'book\s+(\d+)', title, re.IGNORECASE)
        issues.extend([int(n) for n in book_issues])
    
    # If issue field exists and no issues found from title, use it
    if not issues and issue:
        issues.append(issue)
    
    # Remove duplicates and sort
    return sorted(list(set(issues)))


def organize_comic_data(json_file_path: str) -> Dict[str, Any]:
    """
    Main algorithm to organize comic data into hierarchical structure.
    
    Returns:
        {
            'series': {
                'series_name': {
                    'issue_number': [
                        {'variant': '...', 'item': {...}},
                        ...
                    ]
                }
            },
            'combos': {
                'series_name': {
                    'combo_title': {
                        'issues': [1, 2, 3],
                        'item': {...}
                    }
                }
            }
        }
    """
    # Load JSON data
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Initialize structure
    series_structure = defaultdict(lambda: defaultdict(list))
    combo_structure = defaultdict(lambda: defaultdict(dict))
    
    # Process each item
    for item in data:
        # Skip publisher items
        if is_publisher_item(item):
            continue
        
        # Skip items without series
        series_name = item.get('series')
        if not series_name:
            continue
        
        # Normalize series name to merge variations (e.g., "Yagyaa Origins" → "Yagyaa")
        normalized_series_name = normalize_series_name(series_name)
        
        # Handle combo items
        if is_combo_item(item):
            combo_title = item.get('title', 'Unknown Combo')
            issues = extract_combo_issues(item)
            
            combo_structure[normalized_series_name][combo_title] = {
                'issues': issues,
                'item': item
            }
            continue
        
        # Handle regular items
        issue = item.get('issue')
        if issue is None:
            # Try to extract issue from title if not in item
            title = item.get('title', '')
            
            # Try "Issue #" pattern first
            issue_match = re.search(r'issue\s+#?(\d+)', title, re.IGNORECASE)
            if issue_match:
                issue = int(issue_match.group(1))
            else:
                # Try "Book X" pattern
                book_match = re.search(r'book\s+(\d+)', title, re.IGNORECASE)
                if book_match:
                    issue = int(book_match.group(1))
                else:
                    # Try "Vol. X" pattern
                    vol_match = re.search(r'vol\.?\s*(\d+)', title, re.IGNORECASE)
                    if vol_match:
                        issue = int(vol_match.group(1))
                    else:
                        # If no issue found, use None (will be grouped separately)
                        issue = None
        
        variant_info = extract_variant_info(item)
        
        series_structure[normalized_series_name][issue].append({
            'variant': variant_info,
            'item': item
        })
    
    # Sort issues within each series (handle None as a special case)
    for series_name in series_structure:
        # Sort with None issues at the end
        sorted_issues = sorted(
            series_structure[series_name].items(),
            key=lambda x: (x[0] is None, x[0] if x[0] is not None else float('inf'))
        )
        series_structure[series_name] = dict(sorted_issues)
    
    return {
        'series': dict(series_structure),
        'combos': dict(combo_structure)
    }


def generate_code(text: str, prefix: str) -> str:
    """
    Generate a code from text (e.g., "Example Series" -> "ser_example_series").
    
    Args:
        text: The text to convert to code
        prefix: Prefix for the code (e.g., "ser", "iss", "var")
    """
    if not text:
        return f"{prefix}_unknown"
    
    # Convert to lowercase
    code = text.lower()
    
    # Remove special characters, keep only alphanumeric and spaces
    code = re.sub(r'[^a-z0-9\s]', '', code)
    
    # Replace multiple spaces with single space
    code = re.sub(r'\s+', ' ', code)
    
    # Replace spaces with underscores
    code = code.strip().replace(' ', '_')
    
    # Remove multiple underscores
    code = re.sub(r'_+', '_', code)
    
    # Remove leading/trailing underscores
    code = code.strip('_')
    
    # Limit length to avoid too long codes
    if len(code) > 50:
        code = code[:50]
    
    return f"{prefix}_{code}" if code else f"{prefix}_unknown"


def format_as_object_oriented_json(organized_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Format the organized data into object-oriented JSON structure:
    
    {
        "object": "series",
        "name": "Example Series",
        "code": "ser_example_series",
        ...
    }
    
    {
        "object": "list",
        "data": [
            {
                "object": "issue",
                "name": "Example Issue #1",
                "code": "iss_example_issue_1",
                "series_code": "ser_example_series",
                "variants": [
                    {
                        "object": "issue_variant",
                        "name": "Example Issue #1 - Variant A",
                        "code": "var_example_issue_1_a",
                        "language": "Hindi",
                        "binding": "Paperback"
                    }
                ]
            }
        ]
    }
    """
    result = []
    
    # Process series
    for series_name in sorted(organized_data['series'].keys()):
        series_code = generate_code(series_name, "ser")
        
        # Get first item to extract series-level info
        first_item = None
        for issue_num in organized_data['series'][series_name].keys():
            if organized_data['series'][series_name][issue_num]:
                first_item = organized_data['series'][series_name][issue_num][0]['item']
                break
        
        series_obj = {
            "object": "series",
            "name": series_name,
            "code": series_code,
            "publisher": first_item.get('publisher') if first_item else None,
            "url": None,  # Series don't have a single URL
            "description": None
        }
        
        # Remove None values
        series_obj = {k: v for k, v in series_obj.items() if v is not None}
        result.append(series_obj)
    
    # Process issues and variants
    issues_list = []
    
    for series_name in sorted(organized_data['series'].keys()):
        series_code = generate_code(series_name, "ser")
        
        for issue_num in organized_data['series'][series_name].keys():
            variants_data = organized_data['series'][series_name][issue_num]
            
            if not variants_data:
                continue
            
            # Create issue name
            if issue_num is None:
                issue_name = f"{series_name}"
                issue_code = generate_code(f"{series_name} no issue", "iss")
            else:
                issue_name = f"{series_name} #{issue_num}"
                issue_code = generate_code(f"{series_name} issue {issue_num}", "iss")
            
            # Get first variant to extract issue-level info
            first_variant_item = variants_data[0]['item']
            
            # Process variants
            variants_list = []
            variant_counter = 0
            
            for variant_data in variants_data:
                variant_counter += 1
                variant_info = variant_data['variant']
                variant_item = variant_data['item']
                
                # Extract language and binding from variant info and item
                language = variant_item.get('language', '')
                if not language:
                    # Try to extract from variant string
                    if 'hindi' in variant_info.lower():
                        language = 'Hindi'
                    elif 'english' in variant_info.lower():
                        language = 'English'
                    elif 'malayalam' in variant_info.lower():
                        language = 'Malayalam'
                
                binding = variant_item.get('binding', '')
                if not binding:
                    # Try to extract from variant string
                    variant_lower = variant_info.lower()
                    if 'hardcover' in variant_lower or 'hard cover' in variant_lower:
                        binding = 'Hardcover'
                    elif 'hardbound' in variant_lower or 'hard bound' in variant_lower:
                        binding = 'Hardbound'
                    elif 'paperback' in variant_lower or 'paper back' in variant_lower:
                        binding = 'Paperback'
                    elif 'softcover' in variant_lower:
                        binding = 'Softcover'
                
                variant_name = f"{issue_name} - {variant_info}"
                # Remove prefix from issue_code before generating variant code
                issue_code_base = issue_code.replace("iss_", "", 1) if issue_code.startswith("iss_") else issue_code
                variant_code = generate_code(f"{issue_code_base} variant {variant_counter}", "var")
                
                variant_obj = {
                    "object": "issue_variant",
                    "name": variant_name,
                    "code": variant_code,
                    "language": language if language else None,
                    "binding": binding if binding else None,
                    "price": variant_item.get('price'),
                    "original_price": variant_item.get('original_price'),
                    "url": variant_item.get('url'),
                    "cover_image_url": variant_item.get('cover_image_url'),
                    "pages": variant_item.get('pages'),
                    "description": variant_item.get('description')
                }
                
                # Remove None values
                variant_obj = {k: v for k, v in variant_obj.items() if v is not None}
                variants_list.append(variant_obj)
            
            # Create issue object
            issue_obj = {
                "object": "issue",
                "name": issue_name,
                "code": issue_code,
                "series_code": series_code,
                "issue_number": issue_num if issue_num is not None else None,
                "variants": variants_list
            }
            
            # Remove None values
            issue_obj = {k: v for k, v in issue_obj.items() if v is not None}
            issues_list.append(issue_obj)
    
    # Create list object
    list_obj = {
        "object": "list",
        "data": issues_list
    }
    
    result.append(list_obj)
    
    return result


def format_as_hierarchical_json(organized_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format the organized data into the hierarchical JSON structure requested:
    - series_name
      issue 1
        Hindi Variant
        English Variant
        Special Variant
      issue 2
    - combo
      series_1
        issue1, issue2, etc.
    """
    result = {}
    
    # Format series structure
    series_data = {}
    for series_name in sorted(organized_data['series'].keys()):
        issues_data = {}
        for issue_num in organized_data['series'][series_name].keys():
            if issue_num is None:
                issue_key = "no_issue"
            else:
                issue_key = f"issue_{issue_num}"
            
            variants = []
            for variant_data in organized_data['series'][series_name][issue_num]:
                variant_info = {
                    'variant': variant_data['variant'],
                    'price': variant_data['item'].get('price'),
                    'url': variant_data['item'].get('url'),
                    'title': variant_data['item'].get('title')
                }
                variants.append(variant_info)
            
            issues_data[issue_key] = variants
        
        series_data[series_name] = issues_data
    
    result['series'] = series_data
    
    # Format combo structure
    combo_data = {}
    for series_name in sorted(organized_data['combos'].keys()):
        combos_list = []
        for combo_title, combo_info in organized_data['combos'][series_name].items():
            combo_entry = {
                'title': combo_title,
                'issues': combo_info['issues'],
                'price': combo_info['item'].get('price'),
                'url': combo_info['item'].get('url')
            }
            combos_list.append(combo_entry)
        
        combo_data[series_name] = combos_list
    
    result['combos'] = combo_data
    
    return result


def print_structure(organized_data: Dict[str, Any], output_format: str = 'text'):
    """
    Print the organized structure in a readable format.
    
    Args:
        organized_data: Output from organize_comic_data()
        output_format: 'text', 'json', 'hierarchical_json', or 'object_oriented'
    """
    if output_format == 'object_oriented':
        objects = format_as_object_oriented_json(organized_data)
        # Print each object on a separate line (for better readability)
        for obj in objects:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
            print()  # Empty line between objects
        return
    
    if output_format == 'hierarchical_json':
        hierarchical = format_as_hierarchical_json(organized_data)
        print(json.dumps(hierarchical, indent=2, ensure_ascii=False))
        return
    
    if output_format == 'json':
        print(json.dumps(organized_data, indent=2, ensure_ascii=False))
        return
    
    # Print series structure
    print("=" * 80)
    print("SERIES STRUCTURE")
    print("=" * 80)
    
    for series_name in sorted(organized_data['series'].keys()):
        print(f"\n- {series_name}")
        
        for issue_num in organized_data['series'][series_name].keys():
            if issue_num is None:
                print(f"  (No Issue Number)")
            else:
                print(f"  Issue {issue_num}")
            
            variants = organized_data['series'][series_name][issue_num]
            for variant_data in variants:
                variant = variant_data['variant']
                item = variant_data['item']
                price = item.get('price', 'N/A')
                print(f"    - {variant} (₹{price})")
    
    # Print combo structure
    print("\n" + "=" * 80)
    print("COMBOS")
    print("=" * 80)
    
    for series_name in sorted(organized_data['combos'].keys()):
        print(f"\n- {series_name}")
        
        for combo_title, combo_data in organized_data['combos'][series_name].items():
            issues = combo_data['issues']
            item = combo_data['item']
            price = item.get('price', 'N/A')
            
            if issues:
                issues_str = ', '.join(f"Issue {i}" for i in issues)
                print(f"  {combo_title}")
                print(f"    Issues: {issues_str} (₹{price})")
            else:
                print(f"  {combo_title} (₹{price})")


def main():
    """Main function to run the algorithm."""
    import sys
    
    # Default file path
    json_file = 'data/2025-11-17/BullseyePress/2025-11-17-01-00-01-685-AM.json'
    
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    
    # Organize data
    organized_data = organize_comic_data(json_file)
    
    # Print structure
    output_format = 'object_oriented'  # Default to object-oriented JSON
    if len(sys.argv) > 2:
        if sys.argv[2] == '--json' or sys.argv[2] == '--object_oriented':
            output_format = 'object_oriented'
        elif sys.argv[2] == '--hierarchical' or sys.argv[2] == '--hierarchical_json':
            output_format = 'hierarchical_json'
        elif sys.argv[2] == '--text':
            output_format = 'text'
        elif sys.argv[2] == '--save':
            # Save object-oriented JSON format
            output_file = json_file.replace('.json', '_organized.json')
            objects = format_as_object_oriented_json(organized_data)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(objects, f, indent=2, ensure_ascii=False)
            print(f"✅ Organized data saved to: {output_file}")
            return
    
    print_structure(organized_data, output_format)
    
    # Optionally save to file
    if len(sys.argv) > 3 and sys.argv[3] == '--save':
        output_file = json_file.replace('.json', '_organized.json')
        if output_format == 'object_oriented':
            objects = format_as_object_oriented_json(organized_data)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(objects, f, indent=2, ensure_ascii=False)
        elif output_format == 'hierarchical_json':
            hierarchical = format_as_hierarchical_json(organized_data)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(hierarchical, f, indent=2, ensure_ascii=False)
        else:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(organized_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Organized data saved to: {output_file}")


if __name__ == '__main__':
    main()

