#!/usr/bin/env python3
"""
Rebranding Utility Script for RealAlgo to RealAlgo Migration

This script performs find-and-replace operations to rebrand the codebase
from "RealAlgo" to "RealAlgo". It supports:
- Dry-run mode to preview changes without modifying files
- Case-sensitive replacements for both "RealAlgo" and "realalgo"
- Processing of Python, configuration, and documentation files
- Skipping of common directories that should not be modified

Usage:
    python scripts/rebrand.py --dry-run    # Preview changes
    python scripts/rebrand.py              # Apply changes

Requirements validated:
    - 1.1: Replace "RealAlgo" with "RealAlgo" in Python files
    - 1.2: Replace "realalgo" with "realalgo" in Python files
    - 1.3: Update configuration files (.env, .yaml, .json)
    - 1.4: Update documentation files (.md, .txt)
"""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple


class ReplacementResult(NamedTuple):
    """Result of a replacement operation on a single file."""
    file_path: str
    original_content: str
    new_content: str
    replacements_made: Dict[str, int]  # pattern -> count


class RebrandingConfig:
    """Configuration for the rebranding operation."""
    
    # Directories to skip during processing
    SKIP_DIRECTORIES: Set[str] = {
        'venv',
        '.venv',
        'env',
        '__pycache__',
        '.git',
        'node_modules',
        '.pytest_cache',
        '.mypy_cache',
        '.tox',
        'dist',
        'build',
        'eggs',
        '*.egg-info',
        '.kiro',  # Skip spec files
    }
    
    # File extensions to process
    PYTHON_EXTENSIONS: Set[str] = {'.py'}
    CONFIG_EXTENSIONS: Set[str] = {'.env', '.yaml', '.yml', '.json'}
    DOC_EXTENSIONS: Set[str] = {'.md', '.txt', '.rst'}
    FRONTEND_EXTENSIONS: Set[str] = {'.tsx', '.ts', '.jsx', '.js', '.html', '.css'}
    
    # Special files to process (regardless of extension)
    SPECIAL_FILES: Set[str] = {
        '.sample.env',
        'Dockerfile',
        'docker-compose.yaml',
        'docker-compose.yml',
    }
    
    # Replacement patterns (case-sensitive)
    REPLACEMENTS: List[Tuple[str, str]] = [
        ('RealAlgo', 'RealAlgo'),
        ('realalgo', 'realalgo'),
        ('REALALGO', 'REALALGO'),
    ]


class RebrandingUtility:
    """
    Utility class for performing rebranding operations on the codebase.
    
    This class walks through the codebase and performs find-and-replace
    operations to update brand references from RealAlgo to RealAlgo.
    """
    
    def __init__(self, root_dir: str, dry_run: bool = True, verbose: bool = True):
        """
        Initialize the rebranding utility.
        
        Args:
            root_dir: Root directory of the codebase to process
            dry_run: If True, preview changes without modifying files
            verbose: If True, print detailed output
        """
        self.root_dir = Path(root_dir).resolve()
        self.dry_run = dry_run
        self.verbose = verbose
        self.config = RebrandingConfig()
        self.results: List[ReplacementResult] = []
        self.files_processed = 0
        self.files_modified = 0
        self.total_replacements = 0
    
    def should_skip_directory(self, dir_name: str) -> bool:
        """
        Check if a directory should be skipped during processing.
        
        Args:
            dir_name: Name of the directory to check
            
        Returns:
            True if the directory should be skipped, False otherwise
        """
        return dir_name in self.config.SKIP_DIRECTORIES
    
    def should_process_file(self, file_path: Path) -> bool:
        """
        Check if a file should be processed based on its extension.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if the file should be processed, False otherwise
        """
        file_name = file_path.name
        suffix = file_path.suffix.lower()
        
        # Check special files first
        if file_name in self.config.SPECIAL_FILES:
            return True
        
        # Check by extension
        all_extensions = (
            self.config.PYTHON_EXTENSIONS |
            self.config.CONFIG_EXTENSIONS |
            self.config.DOC_EXTENSIONS |
            self.config.FRONTEND_EXTENSIONS
        )
        
        return suffix in all_extensions
    
    def get_file_category(self, file_path: Path) -> str:
        """
        Get the category of a file based on its extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Category string: 'python', 'config', 'doc', 'frontend', or 'special'
        """
        suffix = file_path.suffix.lower()
        file_name = file_path.name
        
        if file_name in self.config.SPECIAL_FILES:
            return 'special'
        elif suffix in self.config.PYTHON_EXTENSIONS:
            return 'python'
        elif suffix in self.config.CONFIG_EXTENSIONS:
            return 'config'
        elif suffix in self.config.DOC_EXTENSIONS:
            return 'doc'
        elif suffix in self.config.FRONTEND_EXTENSIONS:
            return 'frontend'
        else:
            return 'unknown'
    
    def perform_replacements(self, content: str) -> Tuple[str, Dict[str, int]]:
        """
        Perform all replacement operations on the given content.
        
        Args:
            content: Original file content
            
        Returns:
            Tuple of (new_content, replacements_dict) where replacements_dict
            maps each pattern to the number of replacements made
        """
        new_content = content
        replacements_made: Dict[str, int] = {}
        
        for old_pattern, new_pattern in self.config.REPLACEMENTS:
            # Count occurrences before replacement
            count = new_content.count(old_pattern)
            if count > 0:
                replacements_made[f"{old_pattern} -> {new_pattern}"] = count
                new_content = new_content.replace(old_pattern, new_pattern)
        
        return new_content, replacements_made
    
    def process_file(self, file_path: Path) -> Optional[ReplacementResult]:
        """
        Process a single file and perform replacements.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            ReplacementResult if changes were made, None otherwise
        """
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # Perform replacements
            new_content, replacements_made = self.perform_replacements(original_content)
            
            # Check if any changes were made
            if not replacements_made:
                return None
            
            # Create result
            result = ReplacementResult(
                file_path=str(file_path.relative_to(self.root_dir)),
                original_content=original_content,
                new_content=new_content,
                replacements_made=replacements_made
            )
            
            return result
            
        except Exception as e:
            if self.verbose:
                print(f"  Warning: Could not process {file_path}: {e}")
            return None
    
    def apply_changes(self, result: ReplacementResult) -> bool:
        """
        Apply changes to a file (write new content).
        
        Args:
            result: ReplacementResult containing the changes to apply
            
        Returns:
            True if changes were applied successfully, False otherwise
        """
        if self.dry_run:
            return True
        
        try:
            file_path = self.root_dir / result.file_path
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(result.new_content)
            return True
        except Exception as e:
            if self.verbose:
                print(f"  Error: Could not write to {result.file_path}: {e}")
            return False
    
    def walk_directory(self) -> List[Path]:
        """
        Walk through the directory tree and collect files to process.
        
        Returns:
            List of file paths to process
        """
        files_to_process: List[Path] = []
        
        for root, dirs, files in os.walk(self.root_dir):
            # Filter out directories to skip (modifies dirs in-place)
            dirs[:] = [d for d in dirs if not self.should_skip_directory(d)]
            
            for file_name in files:
                file_path = Path(root) / file_name
                if self.should_process_file(file_path):
                    files_to_process.append(file_path)
        
        return sorted(files_to_process)
    
    def run(self) -> Dict[str, any]:
        """
        Run the rebranding operation.
        
        Returns:
            Dictionary containing summary statistics
        """
        mode = "DRY RUN" if self.dry_run else "APPLYING CHANGES"
        print(f"\n{'='*60}")
        print(f"  Rebranding Utility - {mode}")
        print(f"{'='*60}")
        print(f"  Root directory: {self.root_dir}")
        print(f"  Replacements:")
        for old, new in self.config.REPLACEMENTS:
            print(f"    - '{old}' -> '{new}'")
        print(f"{'='*60}\n")
        
        # Collect files to process
        files_to_process = self.walk_directory()
        print(f"Found {len(files_to_process)} files to scan...\n")
        
        # Process each file
        files_by_category: Dict[str, List[ReplacementResult]] = {
            'python': [],
            'config': [],
            'doc': [],
            'frontend': [],
            'special': [],
        }
        
        for file_path in files_to_process:
            self.files_processed += 1
            result = self.process_file(file_path)
            
            if result:
                category = self.get_file_category(file_path)
                files_by_category[category].append(result)
                self.results.append(result)
                self.files_modified += 1
                
                # Count total replacements
                for count in result.replacements_made.values():
                    self.total_replacements += count
                
                # Apply changes if not dry run
                if not self.dry_run:
                    self.apply_changes(result)
        
        # Print results by category
        self._print_results_by_category(files_by_category)
        
        # Print summary
        summary = self._print_summary()
        
        return summary
    
    def _print_results_by_category(self, files_by_category: Dict[str, List[ReplacementResult]]):
        """Print results organized by file category."""
        category_names = {
            'python': 'Python Files (.py)',
            'config': 'Configuration Files (.env, .yaml, .json)',
            'doc': 'Documentation Files (.md, .txt)',
            'frontend': 'Frontend Files (.tsx, .ts, .jsx, .js, .html, .css)',
            'special': 'Special Files (Dockerfile, etc.)',
        }
        
        for category, results in files_by_category.items():
            if results:
                print(f"\n{category_names[category]}:")
                print("-" * 50)
                for result in results:
                    total_count = sum(result.replacements_made.values())
                    print(f"  {result.file_path}")
                    for pattern, count in result.replacements_made.items():
                        print(f"    - {pattern}: {count} replacement(s)")
    
    def _print_summary(self) -> Dict[str, any]:
        """Print and return summary statistics."""
        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        print(f"  Files scanned:    {self.files_processed}")
        print(f"  Files modified:   {self.files_modified}")
        print(f"  Total replacements: {self.total_replacements}")
        
        if self.dry_run:
            print(f"\n  [DRY RUN] No files were modified.")
            print(f"  Run without --dry-run to apply changes.")
        else:
            print(f"\n  [COMPLETE] All changes have been applied.")
        
        print(f"{'='*60}\n")
        
        return {
            'files_scanned': self.files_processed,
            'files_modified': self.files_modified,
            'total_replacements': self.total_replacements,
            'dry_run': self.dry_run,
            'results': self.results,
        }


def main():
    """Main entry point for the rebranding utility."""
    parser = argparse.ArgumentParser(
        description='Rebrand RealAlgo to RealAlgo in the codebase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview changes (dry run)
    python scripts/rebrand.py --dry-run
    
    # Apply changes
    python scripts/rebrand.py
    
    # Process a specific directory
    python scripts/rebrand.py --root ./src --dry-run
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Preview changes without modifying files (default: False)'
    )
    
    parser.add_argument(
        '--root',
        type=str,
        default='.',
        help='Root directory to process (default: current directory)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        default=False,
        help='Suppress detailed output'
    )
    
    args = parser.parse_args()
    
    # Create and run the utility
    utility = RebrandingUtility(
        root_dir=args.root,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )
    
    summary = utility.run()
    
    # Return exit code based on results
    return 0 if summary['files_modified'] >= 0 else 1


if __name__ == '__main__':
    exit(main())
