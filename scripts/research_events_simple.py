#!/usr/bin/env python3
"""
Simple Event Date Research using Gemini API

A simpler alternative that uses the standard Gemini 2.5 Flash model
instead of Deep Research. Faster but may require more manual verification.

Usage:
    python scripts/research_events_simple.py --year 2027
    python scripts/research_events_simple.py --year 2027 --api-key YOUR_KEY

Requirements:
    pip install openai pandas

Note: Uses OpenAI-compatible API that's pre-configured in the environment.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed.")
    print("Install with: pip install openai")
    sys.exit(1)


class SimpleEventResearcher:
    """Simple event date researcher using Gemini 2.5 Flash."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with OpenAI-compatible client."""
        # The environment already has OPENAI_API_KEY set up
        self.client = OpenAI()  # Pre-configured to use Gemini
        self.model = "gemini-2.5-flash"
    
    def load_recurring_events(self, filepath: str) -> pd.DataFrame:
        """Load the existing recurring event mapping file."""
        df = pd.read_csv(filepath)
        print(f"✓ Loaded {len(df)} recurring events from {filepath}")
        return df
    
    def research_event_batch(
        self, 
        events: List[str], 
        target_year: int
    ) -> str:
        """Research a batch of events using Gemini."""
        
        event_list = "\n".join([f"- {event}" for event in events])
        
        prompt = f"""You are a research assistant helping to find exact dates for events in {target_year}.

Please research the following events and provide their exact dates in {target_year}:

{event_list}

For each event, provide:
1. Event name (exactly as listed)
2. Start date (YYYY-MM-DD format)
3. End date (YYYY-MM-DD format)
4. Confidence (High/Medium/Low)

Format your response as a CSV table:
```csv
event_name,start_date,end_date,confidence
memorial_day,{target_year}-05-31,{target_year}-05-31,High
...
```

Important:
- For US federal holidays (Memorial Day, Labor Day), calculate the exact date
- For conventions (CES, SEMA, etc.), find official announced dates
- If not announced, estimate based on historical patterns (mark as Medium/Low confidence)
- Single-day events: start_date = end_date
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant specializing in event dates and calendars."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for factual accuracy
        )
        
        return response.choices[0].message.content
    
    def parse_response(self, response: str, target_year: int) -> List[Dict]:
        """Parse the model's response into structured data."""
        
        results = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            # Skip empty, markdown, and header lines
            if not line or line.startswith('#') or line.startswith('```'):
                continue
            if 'event_name' in line.lower() or 'event' in line.lower() and 'start' in line.lower():
                continue
            
            # Parse CSV-like lines
            if ',' in line and str(target_year) in line:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    results.append({
                        'event_name': parts[0],
                        f'start_{target_year}': parts[1],
                        f'end_{target_year}': parts[2],
                        'confidence': parts[3] if len(parts) > 3 else 'Medium'
                    })
        
        return results
    
    def research_all_events(
        self, 
        events_df: pd.DataFrame, 
        target_year: int,
        batch_size: int = 10
    ) -> pd.DataFrame:
        """Research all events in batches."""
        
        event_names = events_df['event_family'].tolist()
        total_events = len(event_names)
        all_results = []
        
        print(f"\n🔍 Researching {total_events} events in batches of {batch_size}...")
        
        for i in range(0, total_events, batch_size):
            batch = event_names[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_events + batch_size - 1) // batch_size
            
            print(f"\n   Batch {batch_num}/{total_batches}: {len(batch)} events")
            
            try:
                response = self.research_event_batch(batch, target_year)
                parsed = self.parse_response(response, target_year)
                all_results.extend(parsed)
                print(f"   ✓ Parsed {len(parsed)} results")
                
                # Rate limiting: wait between batches
                if i + batch_size < total_events:
                    time.sleep(2)
            
            except Exception as e:
                print(f"   ✗ Error in batch {batch_num}: {e}")
                continue
        
        # Convert to DataFrame
        if all_results:
            results_df = pd.DataFrame(all_results)
            print(f"\n✓ Total results: {len(results_df)} events")
            return results_df
        else:
            print("\n✗ No results parsed")
            return None
    
    def merge_with_existing(
        self, 
        existing_df: pd.DataFrame, 
        new_data_df: pd.DataFrame, 
        target_year: int
    ) -> pd.DataFrame:
        """Merge new year data with existing mapping."""
        
        print(f"\n🔗 Merging {target_year} data with existing mapping...")
        
        merged = existing_df.copy()
        
        # Create mapping from event_name to dates
        year_cols = [f'start_{target_year}', f'end_{target_year}']
        for col in year_cols:
            if col in new_data_df.columns:
                mapping = dict(zip(new_data_df['event_name'], new_data_df[col]))
                # Try to match by event_family
                merged[col] = merged['event_family'].map(mapping)
        
        # Count successful matches
        matched = merged[f'start_{target_year}'].notna().sum()
        print(f"✓ Matched {matched}/{len(merged)} events")
        
        return merged
    
    def save_results(
        self, 
        df: pd.DataFrame, 
        output_path: str,
        target_year: int
    ):
        """Save the updated mapping file."""
        
        df.to_csv(output_path, index=False)
        print(f"✓ Saved updated mapping to: {output_path}")
        
        # Save metadata
        metadata = {
            'target_year': target_year,
            'research_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'model': self.model,
            'events_total': len(df)
        }
        metadata_path = output_path.replace('.csv', f'_metadata_{target_year}.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"✓ Saved metadata to: {metadata_path}")


def main():
    """Main execution function."""
    
    parser = argparse.ArgumentParser(
        description='Simple event date research using Gemini 2.5 Flash'
    )
    parser.add_argument(
        '--year',
        type=int,
        required=True,
        help='Target year for event research (e.g., 2027)'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='data/events/recurring_event_mapping_2025_2026_clean.csv',
        help='Path to existing recurring event mapping file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Path to save updated mapping (default: adds _with_YEAR suffix)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of events to research per batch'
    )
    
    args = parser.parse_args()
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        # Create new file with year suffix
        input_path = Path(args.input)
        output_path = str(input_path.parent / f"{input_path.stem}_with_{args.year}.csv")
    
    print("=" * 70)
    print("  Simple Event Date Research")
    print("  Powered by Gemini 2.5 Flash")
    print("=" * 70)
    print(f"\nTarget year: {args.year}")
    print(f"Input file:  {args.input}")
    print(f"Output file: {output_path}")
    print(f"Batch size:  {args.batch_size}")
    print()
    
    try:
        # Initialize researcher
        researcher = SimpleEventResearcher()
        
        # Load existing events
        events_df = researcher.load_recurring_events(args.input)
        
        # Research all events
        new_data_df = researcher.research_all_events(
            events_df, args.year, args.batch_size
        )
        
        if new_data_df is not None and len(new_data_df) > 0:
            # Merge with existing data
            updated_df = researcher.merge_with_existing(
                events_df, new_data_df, args.year
            )
            
            # Save results
            researcher.save_results(updated_df, output_path, args.year)
            
            print("\n" + "=" * 70)
            print("✓ SUCCESS!")
            print("=" * 70)
            print(f"\nYour recurring event mapping has been updated with {args.year} dates.")
            print(f"\nNext steps:")
            print(f"1. Review the output file: {output_path}")
            print(f"2. Verify the dates are correct (especially Medium/Low confidence)")
            print(f"3. Manually fix any incorrect dates")
            print(f"4. Copy to: data/events/recurring_event_mapping_2025_2026_clean.csv")
            print(f"5. Update config.yaml: forecast_start: {args.year}-01-01")
            print(f"6. Run forecasting: python -m src.forecasting.main")
            print()
        
        else:
            print("\n✗ No results obtained. Please try again or check API access.")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
