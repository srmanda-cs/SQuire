LLVMCONFIG ?= llvm-config

CXX      ?= g++

# Compile flags: now including -fPIC
CXXFLAGS += -std=c++17 -fno-rtti -fno-exceptions -g -fPIC
CXXFLAGS += $(shell $(LLVMCONFIG) --cxxflags)

# Link flags: build a shared library plugin
LDFLAGS  += -shared -fPIC

# We do NOT need to explicitly link LLVM/Clang libs for the plugin:
# unresolved symbols are resolved by clang at load time.
LIBS     :=

all: libNPDChecker.so

libNPDChecker.so: main.o
	$(CXX) $(LDFLAGS) -o $@ $^ $(LIBS)

main.o: main.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f libNPDChecker.so main.o
