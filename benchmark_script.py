import subprocess
import logging
import argparse
from pathlib import Path
import re
import os
import pandas as pd




# Configure logging
def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# Parse command-line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description="Automate benchmarking process for zk experiments.")
    parser.add_argument("--zkllvm-template-path", required=True, help="Path to the zkllvm-template directory.", default="../zkllvm-template")
    args = parser.parse_args()
    return args

def extract_and_convert_time(output):
    """
    Extracts time from the output and converts it to total seconds.

    Args:
    output (str): The output string from the subprocess command.

    Returns:
    float: The total time in seconds, or None if no match is found.
    """
    # Define regular expression pattern to extract the time value
    pattern = r'(\d+):(\d+\.\d+)elapsed'  # Adjusted to directly capture minutes and seconds

    # Search for the time value in the output
    match = re.search(pattern, output)

    if match:
        # Extract the minutes and seconds from the matched groups
        minutes, seconds = match.groups()
        # Convert minutes and seconds to total seconds
        total_seconds = int(minutes) * 60 + float(seconds)
        return total_seconds
    else:
        return None


class BenchmarkTool:
    """A tool for benchmarking zk-SNARK compilation and proof generation."""

    def __init__(self, zkllvm_template_path):
        self.current_dir_path = os.getcwd()
        self.zkllvm_template_path = Path(zkllvm_template_path)
        self.build_src = self.zkllvm_template_path / "build/src"
        self.build = self.zkllvm_template_path / "build"
        self.input_json = self.zkllvm_template_path / "src" / "main-input.json"
        self.assigner_total_gb = None
        self.proof_total_gb = None
        self.assigner_formatted_time = None
        self.proof_formatted_time = None


    def parse_memory_usage(self, file_name):
        """Parse memory usage from a Massif output file.

        Args:
        file_name (str): The name of the Massif output file to parse.

        Returns:
        dict: A dictionary with parsed memory usage information.
        """
        output, _ = self.run_command(f"ms_print {file_name}")
        return self.process_massif_output(output)
  
    @staticmethod
    def process_massif_output(output):
        """Process Massif's ms_print output into a DataFrame.

        Args:
            output (str): The text output from the ms_print command.

        Returns:
            DataFrame: A pandas DataFrame containing the parsed memory usage data.
        """
        lines = output.split("\n")

        # Filtering out the lines that contain the table data start with zero or more whitespace characters followed by one or more digits, then one or more whitespace characters, and finally another digit.
        table_lines = [line for line in lines if re.match(r"^\s*\d+\s+\d", line)]

        # Parsing each line to extract the relevant data
        parsed_tables = []
        for line in table_lines:
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 6:
                parsed_table = {
                    "n": int(parts[0]),
                    "time(i)": parts[1],
                    "total(B)": parts[2],
                    "useful-heap(B)": parts[3],
                    "extra-heap(B)": parts[4],
                    "stacks(B)": parts[5]
                }
                parsed_tables.append(parsed_table)
        
        # Converting str values to Int
        df = pd.DataFrame(parsed_tables)
        df['time(i)'] = df['time(i)'].str.replace(',', '').astype(int)
        df['total(B)'] = df['total(B)'].str.replace(',', '').astype(int)
        df['useful-heap(B)'] = df['useful-heap(B)'].str.replace(',', '').astype(int)
        df['extra-heap(B)'] = df['extra-heap(B)'].str.replace(',', '').astype(int)
        df['stacks(B)'] = df['stacks(B)'].str.replace(',', '').astype(int)

        # List of columns to sum
        columns_to_sum = ['time(i)', 'total(B)', 'useful-heap(B)', 'extra-heap(B)', 'stacks(B)']
        total_row = {col: df[col].sum() if col in columns_to_sum else 'Total' for col in df.columns}
        df_total = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
        return df_total

    def run_command(self, command, cwd=None):
        """
        Execute a shell command in a specified directory and return its output.

        Args:
            command (str): The shell command to execute.
            cwd (str, optional): The directory in which to execute the command. Defaults to None.

        Returns:
            tuple: A tuple containing the stdout and stderr of the executed command.
        """

        # Execute the command in the specified directory (if provided) and capture the output.
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd)

        # Check if the command executed successfully (return code 0).
        if result.returncode != 0:
            logging.error(f"Command failed with error: {result.stderr}")
        else:
            logging.info(f"Command output: {result.stdout}")
        return result.stdout, result.stderr
    
    def verify_build(self):
        """
        Verify that all required files for the build exist in the expected directory.

        Returns:
            bool: True if all required files exist, False otherwise.
        """
        required_files = ["template.ll", "template.crct", "template.tbl"]
        missing_files = [f for f in required_files if not (self.build_src / f).exists()]
        if missing_files:
            logging.error(f"Missing required build files: {', '.join(missing_files)}")
            return False
        return True

    def compile_circuit(self):
        """
        Compile the circuit using the provided script.
        """
        command = f"scripts/run.sh --docker compile"
        self.run_command(command, cwd=self.zkllvm_template_path)

    def measure_assigner_heap_allocation(self):
        """
        Measure the heap allocation of the assigner using Valgrind.
        """
        assigner_gen_command = f"valgrind --massif-out-file=assigner_memory_bench --tool=massif assigner -b {self.build_src}/template.ll -p {self.input_json} -c {self.build_src}/template.crct -t {self.build_src}/template.tbl -e pallas"
        return self.run_command(assigner_gen_command, cwd=self.current_dir_path)

    def measure_proof_generation_heap_allocation(self):
        """
        Measure the heap allocation of the proof generation using Valgrind.
        """
        proof_gen_command = f"valgrind --massif-out-file=proof_memory_bench --tool=massif proof-generator-single-threaded --circuit {self.build}/template.crct --assignment {self.build_src}/template.tbl --proof proof.bin"
        return self.run_command(proof_gen_command, cwd=self.current_dir_path)

    def measure_assigner_execution_time(self):
        """
        Measure the execution time of the assigner using the 'time' command.
        """
        assigner_gen_command = f"time assigner -b {self.build_src}/template.ll -p {self.input_json} -c {self.build_src}/template.crct -t {self.build_src}/template.tbl -e pallas"
        return self.run_command(assigner_gen_command, cwd=self.current_dir_path)

    def measure_proof_generation_execution_time(self):
        """
        Measure the execution time of the proof generation using the 'time' command.
        """
        proof_gen_command = f"time proof-generator-single-threaded --circuit {self.build_src}/template.crct --assignment {self.build_src}/template.tbl --proof {self.build}/proof.bin"
        return self.run_command(proof_gen_command, cwd=self.current_dir_path)

    def display_results(self):
        """
        Displays the benchmark results for both the assigner and proof generation.
        """
        # Check if any benchmark result attribute is None
        if any(value is None for value in [self.assigner_total_gb, self.assigner_formatted_time, self.proof_total_gb, self.proof_formatted_time]):
            logging.error("Benchmark results are incomplete. Please run the benchmark first.")
        else:
            # All attributes are set, proceed to display the results
            print(f"1. Assigner:\n   Memory: {self.assigner_total_gb:.2f}GB,\n   Time: {self.assigner_formatted_time}s")
            print(f"2. Proof:\n   Memory: {self.proof_total_gb:.2f}GB,\n   Time: {self.proof_formatted_time}s")


    def run(self):
        if not self.verify_build():
            logging.error("Build verification failed. Please ensure the zkllvm-template is correctly built before proceeding.")
            return

        while True:
            print("\nBenchmark Tool Menu:")
            print("1. Verify Build")
            print("2. Measure Assigner Heap Allocation")
            print("3. Measure Proof Generation Heap Allocation")
            print("4. Measure Assigner Execution Time")
            print("5. Measure Proof Generation Execution Time")
            print("6. Display Results")
            print("7. Exit")
            choice = input("Enter your choice (1-7): ")
            if choice == '1':
                if not self.verify_build():
                    logging.error("Build verification failed. Please ensure the zkllvm-template is correctly built before proceeding.")
                else:
                    logging.info("Build verification succeeded.")
            elif choice == '2':
                self.measure_assigner_heap_allocation()
                assigner_memory_table = self.parse_memory_usage("assigner_memory_bench")
                assigner_total_bytes = assigner_memory_table.at[assigner_memory_table.index[-1], 'total(B)']
                self.assigner_total_gb = assigner_total_bytes / (2**30)
                logging.info("Assigner heap allocation measured.")
                
            elif choice == '3':
                self.measure_proof_generation_heap_allocation()
                proof_memory_table = self.parse_memory_usage("proof_memory_bench")
                proof_total_bytes = proof_memory_table.at[proof_memory_table.index[-1], 'total(B)']
                self.proof_total_gb = proof_total_bytes / (2**30)
                logging.info("Proof generation heap allocation measured.")

            elif choice == '4':
                _, assigner_time = self.measure_proof_generation_execution_time()
                self.assigner_formatted_time = extract_and_convert_time(assigner_time)
                logging.info("Assigner execution time measured.")
            elif choice == '5':
                _, proof_time = self.measure_proof_generation_execution_time()
                self.proof_formatted_time = extract_and_convert_time(proof_time)
                logging.info("Proof generation execution time measured.")
            elif choice == '6':
                logging.info("Printing Benchmark Details:")
                self.display_results()
            elif choice == '7':
                logging.info("Exiting.")
                break



def main():
    setup_logging()
    args = parse_arguments()
    zkllvm_template_path = Path(args.zkllvm_template_path).resolve()
    logging.debug(f"Using zkllvm-template path: {zkllvm_template_path}")

    benchmark_tool = BenchmarkTool(args.zkllvm_template_path)
    benchmark_tool.run()
    

if __name__ == "__main__":
    main()
