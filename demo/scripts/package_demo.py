#!/usr/bin/env python3
"""
Demo Package Creator

Creates a portable demo package for distribution to prospects and customers.
Includes all necessary files, data, and setup instructions.
"""

import os
import shutil
import json
import zipfile
from datetime import datetime
from pathlib import Path
import argparse


class DemoPackager:
    """Creates portable demo packages"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.demo_dir = self.project_root / "demo"
        
    def create_package(self, package_type: str = "standard", output_dir: str = "build") -> str:
        """Create a demo package"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        package_name = f"entity_resolution_demo_{package_type}_{timestamp}"
        
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        package_dir = output_path / package_name
        
        if package_type == "minimal":
            return self._create_minimal_package(package_dir)
        elif package_type == "complete":
            return self._create_complete_package(package_dir)
        elif package_type == "enterprise":
            return self._create_enterprise_package(package_dir)
        else:  # standard
            return self._create_standard_package(package_dir)
    
    def _create_minimal_package(self, package_dir: Path) -> str:
        """Create minimal demo package (< 10MB)"""
        
        print("Creating minimal demo package...")
        package_dir.mkdir(parents=True, exist_ok=True)
        
        # Core demo files
        self._copy_demo_core(package_dir)
        
        # Generate small sample dataset
        self._generate_sample_data(package_dir, records=1000)
        
        # Create minimal setup script
        self._create_setup_script(package_dir, "minimal")
        
        # Create README
        self._create_package_readme(package_dir, "minimal")
        
        return self._zip_package(package_dir)
    
    def _create_standard_package(self, package_dir: Path) -> str:
        """Create standard demo package (< 50MB)"""
        
        print("Creating standard demo package...")
        package_dir.mkdir(parents=True, exist_ok=True)
        
        # Core demo files
        self._copy_demo_core(package_dir)
        
        # Standard dataset
        self._generate_sample_data(package_dir, records=5000)
        
        # Industry scenarios
        self._copy_industry_scenarios(package_dir)
        
        # Dashboard
        self._copy_dashboard(package_dir)
        
        # Setup script
        self._create_setup_script(package_dir, "standard")
        
        # Documentation
        self._copy_documentation(package_dir)
        
        # Create README
        self._create_package_readme(package_dir, "standard")
        
        return self._zip_package(package_dir)
    
    def _create_complete_package(self, package_dir: Path) -> str:
        """Create complete demo package with all features"""
        
        print("Creating complete demo package...")
        package_dir.mkdir(parents=True, exist_ok=True)
        
        # Everything from standard
        self._copy_demo_core(package_dir)
        self._copy_dashboard(package_dir)
        self._copy_documentation(package_dir)
        
        # Large dataset
        self._generate_sample_data(package_dir, records=10000)
        
        # All industry scenarios
        self._copy_industry_scenarios(package_dir)
        self._generate_all_industry_data(package_dir)
        
        # Source code for customization
        self._copy_source_code(package_dir)
        
        # Setup script
        self._create_setup_script(package_dir, "complete")
        
        # Create README
        self._create_package_readme(package_dir, "complete")
        
        return self._zip_package(package_dir)
    
    def _create_enterprise_package(self, package_dir: Path) -> str:
        """Create enterprise demo package with full source"""
        
        print("Creating enterprise demo package...")
        package_dir.mkdir(parents=True, exist_ok=True)
        
        # Complete project copy (excluding .git, __pycache__, etc.)
        self._copy_full_project(package_dir)
        
        # Pre-generated data for all scenarios
        self._generate_all_demo_data(package_dir)
        
        # Setup script
        self._create_setup_script(package_dir, "enterprise")
        
        # Create README
        self._create_package_readme(package_dir, "enterprise")
        
        return self._zip_package(package_dir)
    
    def _copy_demo_core(self, package_dir: Path):
        """Copy core demo files"""
        demo_dest = package_dir / "demo"
        demo_dest.mkdir(parents=True, exist_ok=True)
        
        # Copy demo scripts
        scripts_src = self.demo_dir / "scripts"
        scripts_dest = demo_dest / "scripts"
        
        if scripts_src.exists():
            shutil.copytree(scripts_src, scripts_dest, ignore=shutil.ignore_patterns('__pycache__'))
        
        # Copy requirements for demo
        req_file = package_dir / "requirements.txt"
        with open(req_file, 'w') as f:
            f.write("""# Entity Resolution Demo Requirements
requests>=2.25.0
python-arango>=7.0.0
python-dotenv>=0.19.0
""")
    
    def _copy_dashboard(self, package_dir: Path):
        """Copy dashboard files"""
        templates_src = self.demo_dir / "templates"
        templates_dest = package_dir / "demo" / "templates"
        
        if templates_src.exists():
            shutil.copytree(templates_src, templates_dest)
    
    def _copy_industry_scenarios(self, package_dir: Path):
        """Copy industry scenario generators"""
        # Industry scenarios are part of scripts, already copied
        pass
    
    def _copy_documentation(self, package_dir: Path):
        """Copy relevant documentation"""
        docs_dest = package_dir / "docs"
        docs_dest.mkdir(exist_ok=True)
        
        # Copy demo-specific docs
        demo_readme = self.demo_dir / "README.md"
        if demo_readme.exists():
            shutil.copy2(demo_readme, docs_dest / "DEMO_README.md")
        
        setup_guide = self.demo_dir / "DEMO_SETUP_GUIDE.md"
        if setup_guide.exists():
            shutil.copy2(setup_guide, docs_dest / "DEMO_SETUP_GUIDE.md")
        
        # Copy main project README
        main_readme = self.project_root / "README.md"
        if main_readme.exists():
            shutil.copy2(main_readme, docs_dest / "PROJECT_README.md")
    
    def _copy_source_code(self, package_dir: Path):
        """Copy source code for customization"""
        src_dest = package_dir / "src"
        src_src = self.project_root / "src"
        
        if src_src.exists():
            shutil.copytree(src_src, src_dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    
    def _copy_full_project(self, package_dir: Path):
        """Copy entire project structure"""
        ignore_patterns = shutil.ignore_patterns(
            '.git', '__pycache__', '*.pyc', '*.pyo', '.pytest_cache',
            '.venv', 'venv', 'node_modules', '.DS_Store', 'build', 'dist'
        )
        
        # Copy main directories
        for item in self.project_root.iterdir():
            if item.is_dir() and item.name not in {'.git', '__pycache__', 'build'}:
                dest_path = package_dir / item.name
                shutil.copytree(item, dest_path, ignore=ignore_patterns)
            elif item.is_file() and item.suffix in {'.py', '.md', '.txt', '.yml', '.yaml', '.json'}:
                shutil.copy2(item, package_dir / item.name)
    
    def _generate_sample_data(self, package_dir: Path, records: int):
        """Generate sample data for demo"""
        print(f"Generating {records} sample records...")
        
        data_dir = package_dir / "demo" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Import and use data generator
        import sys
        sys.path.insert(0, str(self.project_root))
        
        try:
            from demo.scripts.data_generator import DataGenerator
            
            generator = DataGenerator()
            records_data, metadata = generator.generate_dataset(
                total_records=records,
                duplicate_rate=0.2
            )
            
            # Save data
            with open(data_dir / "demo_customers.json", 'w') as f:
                json.dump(records_data, f, indent=2)
            
            with open(data_dir / "demo_metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"Generated {len(records_data)} records with {metadata['duplicate_groups']} duplicate groups")
            
        except ImportError as e:
            print(f"Warning: Could not generate sample data: {e}")
            # Create placeholder files
            with open(data_dir / "README.txt", 'w') as f:
                f.write("Run the data generator to create demo data:\n")
                f.write("python3 demo/scripts/data_generator.py --records 5000 --output-dir demo/data\n")
    
    def _generate_all_industry_data(self, package_dir: Path):
        """Generate all industry scenario data"""
        print("Generating industry scenario data...")
        
        try:
            import sys
            sys.path.insert(0, str(self.project_root))
            from demo.scripts.industry_scenarios import IndustryScenarioGenerator
            
            generator = IndustryScenarioGenerator()
            
            scenarios = {
                'b2b_sales': generator.generate_b2b_sales_scenario(2000),
                'ecommerce': generator.generate_ecommerce_scenario(3000),
                'healthcare': generator.generate_healthcare_scenario(1500),
                'financial': generator.generate_financial_scenario(2500)
            }
            
            scenarios_dir = package_dir / "demo" / "data" / "industry_scenarios"
            scenarios_dir.mkdir(parents=True, exist_ok=True)
            
            for industry, scenario in scenarios.items():
                scenario_file = scenarios_dir / f"{industry}_scenario.json"
                with open(scenario_file, 'w') as f:
                    json.dump(scenario, f, indent=2)
            
            print(f"Generated {len(scenarios)} industry scenarios")
            
        except ImportError as e:
            print(f"Warning: Could not generate industry data: {e}")
    
    def _generate_all_demo_data(self, package_dir: Path):
        """Generate comprehensive demo data for enterprise package"""
        self._generate_sample_data(package_dir, records=25000)
        self._generate_all_industry_data(package_dir)
    
    def _create_setup_script(self, package_dir: Path, package_type: str):
        """Create setup script for the package"""
        setup_script = package_dir / "setup.sh"
        
        script_content = f"""#!/bin/bash
# Entity Resolution Demo Setup Script
# Package Type: {package_type}
# Generated: {datetime.now().isoformat()}

echo "Setting up Entity Resolution Demo ({package_type})..."

# Check Python version
python3 --version || {{
    echo "Error: Python 3.8+ required"
    exit 1
}}

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Generate data if needed
if [ ! -f "demo/data/demo_customers.json" ]; then
    echo "Generating demo data..."
    cd demo/scripts
    python3 data_generator.py --records 5000 --output-dir ../data
    cd ../..
fi

echo "Setup complete!"
echo ""
echo "To run the demo:"
echo "  cd demo/scripts"
echo "  python3 demo_orchestrator.py --auto --records 5000"
echo ""
echo "To view the dashboard:"
echo "  Open demo/templates/demo_dashboard.html in your browser"
echo ""
echo "For more options, see docs/DEMO_SETUP_GUIDE.md"
"""
        
        with open(setup_script, 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(setup_script, 0o755)
        
        # Create Windows version
        setup_bat = package_dir / "setup.bat"
        bat_content = f"""@echo off
REM Entity Resolution Demo Setup Script (Windows)
REM Package Type: {package_type}

echo Setting up Entity Resolution Demo ({package_type})...

REM Check Python
python --version >nul 2>&1 || (
    echo Error: Python 3.8+ required
    exit /b 1
)

REM Install dependencies
echo Installing Python dependencies...
pip install -r requirements.txt

REM Generate data if needed
if not exist "demo\\data\\demo_customers.json" (
    echo Generating demo data...
    cd demo\\scripts
    python data_generator.py --records 5000 --output-dir ..\\data
    cd ..\\..
)

echo Setup complete!
echo.
echo To run the demo:
echo   cd demo\\scripts
echo   python demo_orchestrator.py --auto --records 5000
echo.
echo To view the dashboard:
echo   Open demo\\templates\\demo_dashboard.html in your browser
"""
        
        with open(setup_bat, 'w') as f:
            f.write(bat_content)
    
    def _create_package_readme(self, package_dir: Path, package_type: str):
        """Create package-specific README"""
        readme_content = f"""# Entity Resolution Demo Package ({package_type.title()})

## Quick Start

### Option 1: Automated Setup
```bash
# Run setup script
./setup.sh          # Linux/Mac
setup.bat           # Windows

# Run demo
cd demo/scripts
python3 demo_orchestrator.py --auto --records 5000
```

### Option 2: Manual Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Generate data
cd demo/scripts
python3 data_generator.py --records 5000 --output-dir ../data

# Run demo
python3 demo_orchestrator.py --auto --records 5000
```

## Package Contents

### {package_type.title()} Package Includes:
"""
        
        if package_type == "minimal":
            readme_content += """
- Core demo orchestrator
- Data generator (1K records)
- Basic setup script
- Essential documentation
"""
        elif package_type == "standard":
            readme_content += """
- Complete demo orchestrator
- Data generator (5K records)
- Interactive dashboard
- Industry scenarios
- Comprehensive documentation
- Setup scripts (Linux/Windows)
"""
        elif package_type == "complete":
            readme_content += """
- Full demo suite
- Large dataset (10K records)
- All industry scenarios
- Interactive dashboard
- Source code for customization
- Complete documentation
- Setup and deployment scripts
"""
        elif package_type == "enterprise":
            readme_content += """
- Complete source code
- All demo components
- Large datasets (25K records)
- All industry scenarios
- Interactive dashboard
- Full documentation
- Deployment scripts
- Customization examples
"""
        
        readme_content += f"""

## Demo Options

### 1. Interactive Demo (30 minutes)
```bash
cd demo/scripts
python3 demo_orchestrator.py --records 5000
```

### 2. Automated Demo (15 minutes)
```bash
cd demo/scripts
python3 demo_orchestrator.py --auto --records 5000
```

### 3. Dashboard Demo
Open `demo/templates/demo_dashboard.html` in your browser

### 4. Industry-Specific Demo
```bash
cd demo/scripts
python3 industry_scenarios.py
# Use generated scenarios in demo/data/industry_scenarios/
```

## Business Value Highlights

- **Pairwise F1 0.937 on DBLP-ACM and 0.995 on FEBRL**, measured on public benchmarks
- **Blocking removes 99%+ of candidate comparisons** (99.08–99.96% measured)
- **Deliver 500-3000% first-year ROI** depending on scale
- **Reduce operational costs** by 20-40% across departments

## Technical Advantages

- **ArangoDB's unique FTS+Graph** capabilities in one platform
- **99%+ fewer comparisons** via blocking
- **Incremental resolution** of single records against what is already stored
- **Measured scale** up to 66,879 records (see docs/BENCHMARKS.md#scale-limits)

## Support

- See `docs/DEMO_SETUP_GUIDE.md` for detailed setup instructions
- See `docs/DEMO_README.md` for comprehensive demo documentation
- For technical support: [contact information]
- For sales inquiries: [contact information]

Generated: {datetime.now().isoformat()}
Package Type: {package_type}
"""
        
        with open(package_dir / "README.md", 'w') as f:
            f.write(readme_content)
    
    def _zip_package(self, package_dir: Path) -> str:
        """Create ZIP file of the package"""
        zip_path = f"{package_dir}.zip"
        
        print(f"Creating ZIP package: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(package_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != '__pycache__']
                
                for file in files:
                    if not file.endswith('.pyc'):
                        file_path = Path(root) / file
                        arc_path = file_path.relative_to(package_dir.parent)
                        zipf.write(file_path, arc_path)
        
        # Remove the directory, keep only ZIP
        shutil.rmtree(package_dir)
        
        print(f"Package created: {zip_path}")
        print(f"Package size: {os.path.getsize(zip_path) / 1024 / 1024:.1f} MB")
        
        return zip_path


def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(description='Create Entity Resolution Demo Package')
    parser.add_argument('--type', choices=['minimal', 'standard', 'complete', 'enterprise'], 
                       default='standard', help='Package type to create')
    parser.add_argument('--output', default='build', help='Output directory')
    parser.add_argument('--project-root', default='.', help='Project root directory')
    
    args = parser.parse_args()
    
    packager = DemoPackager(args.project_root)
    package_path = packager.create_package(args.type, args.output)
    
    print(f"\nDemo package created successfully!")
    print(f"Package: {package_path}")
    print(f"Type: {args.type}")
    
    print(f"\nTo distribute:")
    print(f"1. Send the ZIP file to prospects")
    print(f"2. They extract and run ./setup.sh")
    print(f"3. Demo is ready in under 5 minutes")


if __name__ == "__main__":
    main()
