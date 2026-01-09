#!/usr/bin/env python3
"""
Automated Event Date Research using Gemini Deep Research API

This script uses Google's Gemini Deep Research Agent to automatically find
event dates for the forecasting system. It reads the existing recurring event
mapping file and researches the dates for the target year.

Usage:
    python scripts/automate_event_research.py --year 2027
    python scripts/automate_event_research.py --year 2027 --api-key YOUR_KEY

Requirements:
    pip install google-genai pandas

Environment:
    GEMINI_API_KEY: Your Google AI API key (or use --api-key flag)
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
    from google import genai
except ImportError:
    print("ERROR: google-genai package not installed.")
    print("Install with: pip install google-genai")
    sys.exit(1)


class EventDateResearcher:
    """Automates event date research using Gemini Deep Research API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the researcher with API credentials."""
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Set environment variable or use --api-key flag."
            )
        
        # Set the API key in environment for genai client
        os.environ['GEMINI_API_KEY'] = self.api_key
        self.client = genai.Client()
        self.agent = 'deep-research-pro-preview-12-2025'
    
    def load_recurring_events(self, filepath: str) -> pd.DataFrame:
        """Load the existing recurring event mapping file."""
        df = pd.read_csv(filepath)
        print(f"✓ Loaded {len(df)} recurring events from {filepath}")
        return df
    
    def build_research_prompt(self, events_df: pd.DataFrame, target_year: int) -> str:
        """Build a comprehensive research prompt for Gemini."""
        
        # Extract unique event names
        event_list = events_df['event_family'].tolist()
        
        prompt = f"""
Research the exact dates for the following events in {target_year}.

I need precise start and end dates for each event. These are events that impact 
a restaurant in Las Vegas, Nevada. Many are conventions, festivals, and holidays.

**Events to research:**

{self._format_event_list(events_df)}

**Output format required:**

Please provide the results in a structured format with the following for each event:

1. Event name (exactly as listed above)
2. Start date ({target_year}-MM-DD format)
3. End date ({target_year}-MM-DD format)
4. Confidence level (High/Medium/Low)
5. Source (where you found the information)

**Important notes:**

- For holidays that move year-to-year (Memorial Day, Labor Day, Easter), calculate the exact date for {target_year}
- For conventions (CES, SEMA, SHOT Show, etc.), find the official announced dates
- If a date is not yet announced, provide your best estimate based on historical patterns
- For single-day events, start_date = end_date
- Use YYYY-MM-DD format for all dates

**Format the output as a CSV-like table:**

```
event_family,start_{target_year},end_{target_year},confidence,source
memorial_day,{target_year}-05-31,{target_year}-05-31,High,US Federal Holiday Calendar
...
```

Please be thorough and accurate. This data will be used for business forecasting.
"""
        return prompt
    
    def _format_event_list(self, events_df: pd.DataFrame) -> str:
        """Format event list for the prompt."""
        lines = []
        for idx, row in events_df.iterrows():
            event_name = row['event_family']
            category = row.get('category', 'Unknown')
            lines.append(f"- {event_name} ({category})")
        return "\n".join(lines)
    
    def run_research(self, prompt: str, target_year: int) -> str:
        """Execute the research task using Gemini Deep Research."""
        
        print(f"\n🔍 Starting research for {target_year} event dates...")
        print(f"   Agent: {self.agent}")
        print(f"   This may take 2-5 minutes...\n")
        
        try:
            # Start research in background
            interaction = self.client.interactions.create(
                input=prompt,
                agent=self.agent,
                background=True
            )
            
            interaction_id = interaction.id
            print(f"✓ Research started (ID: {interaction_id})")
            
            # Poll for completion
            dots = 0
            while True:
                interaction = self.client.interactions.get(interaction_id)
                
                if interaction.status == "completed":
                    print("\n✓ Research completed!")
                    result = interaction.outputs[-1].text
                    return result
                
                elif interaction.status == "failed":
                    error_msg = getattr(interaction, 'error', 'Unknown error')
                    raise RuntimeError(f"Research failed: {error_msg}")
                
                else:
                    # Show progress
                    print("." * (dots % 4), end="\r", flush=True)
                    dots += 1
                    time.sleep(10)
        
        except Exception as e:
            print(f"\n✗ Research failed: {e}")
            raise
    
    def parse_research_results(self, research_output: str, target_year: int) -> pd.DataFrame:
        """Parse the research output into a structured DataFrame."""
        
        print("\n📊 Parsing research results...")
        
        # Try to extract CSV-like content from the output
        # Look for lines that match the expected format
        lines = research_output.split('\n')
        
        data_rows = []
        for line in lines:
            # Skip empty lines and headers
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('event_family'):
                continue
            
            # Try to parse as CSV
            if ',' in line and target_year in line:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    data_rows.append(parts)
        
        if not data_rows:
            print("⚠ Warning: Could not automatically parse results.")
            print("   Saving raw output for manual review.")
            return None
        
        # Create DataFrame
        columns = ['event_family', f'start_{target_year}', f'end_{target_year}', 
                   'confidence', 'source']
        df = pd.DataFrame(data_rows, columns=columns[:len(data_rows[0])])
        
        print(f"✓ Parsed {len(df)} events")
        return df
    
    def merge_with_existing(
        self, 
        existing_df: pd.DataFrame, 
        new_data_df: pd.DataFrame, 
        target_year: int
    ) -> pd.DataFrame:
        """Merge new year data with existing recurring event mapping."""
        
        print(f"\n🔗 Merging {target_year} data with existing mapping...")
        
        # Merge on event_family
        merged = existing_df.copy()
        
        # Add new year columns
        year_cols = [f'start_{target_year}', f'end_{target_year}']
        for col in year_cols:
            if col in new_data_df.columns:
                # Create a mapping dict
                mapping = dict(zip(new_data_df['event_family'], new_data_df[col]))
                merged[col] = merged['event_family'].map(mapping)
        
        print(f"✓ Added columns: {year_cols}")
        return merged
    
    def save_results(
        self, 
        df: pd.DataFrame, 
        output_path: str,
        raw_research: str,
        target_year: int
    ):
        """Save the updated mapping file and raw research output."""
        
        # Save updated CSV
        df.to_csv(output_path, index=False)
        print(f"✓ Saved updated mapping to: {output_path}")
        
        # Save raw research output
        raw_output_path = output_path.replace('.csv', f'_raw_research_{target_year}.txt')
        with open(raw_output_path, 'w') as f:
            f.write(raw_research)
        print(f"✓ Saved raw research to: {raw_output_path}")
        
        # Save metadata
        metadata = {
            'target_year': target_year,
            'research_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'agent': self.agent,
            'events_researched': len(df)
        }
        metadata_path = output_path.replace('.csv', f'_metadata_{target_year}.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"✓ Saved metadata to: {metadata_path}")


def main():
    """Main execution function."""
    
    parser = argparse.ArgumentParser(
        description='Automate event date research using Gemini Deep Research API'
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
        help='Path to save updated mapping (default: overwrites input)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='Google AI API key (or set GEMINI_API_KEY env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show the research prompt without executing'
    )
    
    args = parser.parse_args()
    
    # Determine output path
    output_path = args.output or args.input
    
    print("=" * 70)
    print("  Automated Event Date Research")
    print("  Powered by Gemini Deep Research API")
    print("=" * 70)
    print(f"\nTarget year: {args.year}")
    print(f"Input file:  {args.input}")
    print(f"Output file: {output_path}")
    print()
    
    try:
        # Initialize researcher
        researcher = EventDateResearcher(api_key=args.api_key)
        
        # Load existing events
        events_df = researcher.load_recurring_events(args.input)
        
        # Build research prompt
        prompt = researcher.build_research_prompt(events_df, args.year)
        
        if args.dry_run:
            print("\n" + "=" * 70)
            print("RESEARCH PROMPT (dry-run mode)")
            print("=" * 70)
            print(prompt)
            print("=" * 70)
            print("\nDry-run complete. No research executed.")
            return
        
        # Execute research
        research_output = researcher.run_research(prompt, args.year)
        
        # Parse results
        new_data_df = researcher.parse_research_results(research_output, args.year)
        
        if new_data_df is not None:
            # Merge with existing data
            updated_df = researcher.merge_with_existing(
                events_df, new_data_df, args.year
            )
            
            # Save results
            researcher.save_results(
                updated_df, output_path, research_output, args.year
            )
            
            print("\n" + "=" * 70)
            print("✓ SUCCESS!")
            print("=" * 70)
            print(f"\nYour recurring event mapping has been updated with {args.year} dates.")
            print(f"\nNext steps:")
            print(f"1. Review the output file: {output_path}")
            print(f"2. Verify the dates are correct")
            print(f"3. Update config.yaml: forecast_start: {args.year}-01-01")
            print(f"4. Run forecasting: python -m src.forecasting.main")
            print()
        
        else:
            print("\n" + "=" * 70)
            print("⚠ MANUAL REVIEW REQUIRED")
            print("=" * 70)
            print("\nThe research completed, but automatic parsing failed.")
            print(f"Please review the raw output and manually update the CSV.")
            print()
    
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
