# QA test assignment

In =nil; everything revolves around zero-knowledge circuit. The task is write an automation script for our toolchain zk experiments in this assignment. You will need to write a simple scripts in python which will automate the following benchmarking process. For this you will need a Linux x86 system. If your system is not x86, feel free to use a server. 

You will need to:

1. Install all the requirements
2. Write a python script for automating the benchmarking steps below

Criteria:

1. Code cleanness
2. Work with the linux tooling inside your script

**tip:**

Feel free to use different tools such as cat, grep, awk if you want to find some output in your file

### Prerequisites

You will need to build the toolchain on you machine :

1. Build the assigner https://github.com/nilFoundation/zkllvm
    
    You will need to build the assigner following the guide in the zkllvm repo. There might be some issues the boost lib version, If the assigner can’t be built on
    
2. Install the [proof-generator](https://github.com/NilFoundation/proof-producer)
    
    Proof generator will be needed to produce the proof
    
3. Clone [zkllvm-template](https://github.com/NilFoundation/zkllvm-template) and install dependencies from readme
    
    We will need this repo to compile experiments
    
4. Install the valgrind and massif-visualizer
    
    ```jsx
    sudo apt-get install valgrind massif-visualizer
    ```
    

### Benchmarking

Not that we have all the dependencies ready, we can try to benchmark our circuit. Open the zkllvm-tepmlate repo and change the content of your src/main.cpp to this code:

```cpp
#include <nil/crypto3/hash/algorithm/hash.hpp>
#include <nil/crypto3/hash/sha2.hpp>

using namespace nil::crypto3;

bool is_same(size_t a, size_t b)
{
    return a == b;
}

[[circuit]] bool validate_number(
    [[private_input]] size_t a)
{
    return is_same(a, 5);
}
```

Then change src/main-input.json:

```cpp
[
    {
        "int": 5
    }
]
```

1. Head back in the zkllvm-template root and compile circuit:
    
    ```bash
    scripts/run.sh --docker compile
    ```
    
2. Now that we compiled the circuit we can measure heap allocation using **valgrind**
    
    ```bash
    valgrind --tool=massif assigner -b build/src/template.ll -p ./src/main-input.json -c build/src/template.crct -t build/src/template.tbl -e pallas
    ```
    
    **reading valgrind ouput**
    
    ```bash
    ms_print massif.out.917835
    ```
    
    You will see the following table:
    
    ```cpp
    --------------------------------------------------------------------------------
      n        time(i)         total(B)   useful-heap(B) extra-heap(B)    stacks(B)
    --------------------------------------------------------------------------------
     58     79,828,659      320,303,704      320,282,580        21,124            0
     59     79,896,889      320,352,768      320,331,684        21,084            0
     60     80,032,320      320,380,416      320,359,332        21,084            0
     61     80,212,509      320,417,280      320,396,196        21,084            0
     62     80,344,400      320,359,280      320,338,212        21,068            0
     63     80,395,247      320,313,328      320,291,748        21,580            0
     64     80,445,601      320,300,640      320,279,684        20,956            0
     65     80,498,746      320,281,064      320,261,724        19,340            0
     66     80,549,602          240,824          228,713        12,111            0
     67     80,600,002          153,464          152,036         1,428            0
    ```
    
    Where:
    
    - **n**: Snapshot number.
    - **time(i)**: The time at which the snapshot was taken, measured in instructions executed up to that point.
    - **total(B)**: Total memory usage (in bytes) at the time of the snapshot.
    - **useful-heap(B)**: The amount of heap memory that was deemed useful at the time of the snapshot.
    - **extra-heap(B)**: The amount of heap memory used for management overhead.
    - **stacks(B)**: The amount of memory used by the program's stack (this is 0 in your output, indicating that stack usage was not measured).
    
    You will need to check several tables and calculate the amount of memory used.
    
    **Time calculation:**
    
    Also you will need to run the assigner with the time command because we want to know how long assenger was running and we don’t want the overhead from valgrind
    
    ```bash
    time assigner -b build/src/template.ll -p ./src/main-input.json -c build/src/template.crct -t build/src/template.tbl -e pallas
    ```
    
3. **Measure proof generation**
    
    Now we can measure proof generation with the files output we received from the assigner
    
    ```bash
    valgrind --tool=massif proof-generator-single-threaded --circuit  build/src/template.crct --assignment build/src/template.tbl --proof build/proof.bin
    ```
    
    **reading valgrind ouput**
    
    ```bash
    ms_print massif.out.917835
    ```
    
    **Time calculation:**
    
    ```bash
    time proof-generator-single-threaded --circuit  build/src/template.crct --assignment build/src/template.tbl --proof build/proof.bin
    ```
    
4. **Measure proof generation**
    
    Now we only need to verify that the proof is correct
    
    ```bash
    valgrind --tool=massif proof-generator-single-threaded --circuit  build/src/template.crct --assignment build/src/template.tbl --proof build/proof.bin
    ```
    

Now we can extrapolate this results for the bigger input. In the end you should have the following data:

1. Assigner 
    1. memory: 0.5gb
    2. time: 180s
2. Proof 
    1. memory: 0.8gb
    2. time: 240s