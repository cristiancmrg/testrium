# **Testrium**

<div style="display: flex; align-items: center;">
  <img src="https://github.com/letalboy/Spectrum/assets/63066865/cf9c60e7-9eba-474c-8cc1-b246e661fd5c" alt="Testrium Logo" width="200" height="200" style="margin-right: 20px;">
  <div>
    <p>**Testrium** is a versatile and advanced testing framework designed to probe and validate complex systems. With powerful tools for data processing, monitoring, and ensuring system integrity, Testrium enhances your development workflow, making it an essential asset for modern testing needs.</p>
  </div>
</div>

## **Key Features**

- **Better Organization of Tests**: Streamline your testing process with improved test management and categorization.
- **Easy Testing of Async or Parallelized Dependent Tests**: Simplify the testing of asynchronous or parallel workflows with built-in support.
- **Historic Performance Comparison and Evaluation**: Track and compare test performance over time for better insights.
- **Custom Behavior Through Callback Systems**: Customize test behaviors using flexible callback mechanisms.
- **Manipulation of Test Flows**: Gain control over test execution flows to suit various testing scenarios.
- **Highly Configurable and Expandable**: Tailor Testrium to your specific needs with extensive configuration options.

## **Installation**

**Testrium** can be installed using [Poetry](https://python-poetry.org/) or [pip](https://pip.pypa.io/en/stable/).

### **Using Poetry**

```bash
poetry add testrium
```

### **Using pip**

```bash
pip install testrium
```

### **Example Usage**

See the [developer guide](docs/developer-guide.md) for a practical walkthrough of how to structure Testrium scenarios, define units, emit probes, and verify coordinated multi-process behavior.

### **README Description for Testrium**

---

# **Testrium: Cutting-Edge Testing with Probes and Validation**

**Testrium** is a modern testing framework designed to meet the challenges of contemporary, complex systems. Moving beyond traditional testing tools, **Testrium** offers advanced capabilities for probing and validating intricate behaviors and interactions.

## **Why Testrium?**

### 1. **Built for Complexity**
- **Probing and Validation**: **Testrium** excels in environments where traditional testing frameworks fall short, such as asynchronous, parallel, or interdependent scenarios. It provides tools to insert probes and validate system behavior in real-time.
- **Sophisticated Setups**: Easily define complex setups, such as socket communication or multi-component integrations, without being constrained by traditional return-based configurations.

### 2. **Dynamic Probes and Checks**
- **Probes**: Integrate probes within your tests to capture and analyze specific events and state changes, offering detailed insights into system behavior and interactions.
- **Validation Callbacks**: Utilize a flexible callback system to perform additional validation and cleanup during and after tests. This dynamic mechanism allows tests to adapt based on real-time results.

### 3. **Efficient Parallel Execution**
- **Concurrent Testing**: Execute multiple tests in parallel to save time and simulate real-world scenarios where different components operate concurrently. **Testrium** manages parallel execution efficiently, ensuring accurate results.
- **Coordinated Validation**: Validate complex interactions across multiple tests, ensuring system integrity and consistency under varied conditions.

### 4. **Configurable and Adaptable**
- **Config-Driven Design**: Customize test behavior, manage setups, and control execution through configuration files. **Testrium**’s design offers unmatched flexibility, aligning the testing environment precisely with your project’s needs.

## **Why Build from Scratch?**

### 1. **Addressing Existing Limitations**
- **Traditional Tools**: Existing frameworks like `pytest` often lack the specialized capabilities required for probing and validating complex, event-driven systems.
- **Innovative Features**: Developing **Testrium** from the ground up allows for the integration of advanced features such as dynamic probes and validation callbacks, free from the constraints of existing architectures.

### 2. **Optimized for Modern Development**
- **Focused Use Cases**: **Testrium** is tailored for scenarios involving asynchronous behaviors, parallel processes, and complex system interactions, where traditional tools may fall short.
- **Future-Ready**: As software development evolves, **Testrium** is designed to adapt, ensuring it remains effective and relevant for new testing challenges.

## **Goals of Testrium**

### 1. **Simplify Complex Testing**
- Provide developers with intuitive tools for testing event-driven and asynchronous systems, reducing the complexity of advanced validation scenarios.

### 2. **Enhance Test Coverage**
- Enable comprehensive testing of interactions across components, improving the reliability and robustness of complex systems.

### 3. **Promote Flexibility and Control**
- Offer a highly adaptable testing framework that aligns with diverse project requirements, allowing custom setups, validations, and test flows.

### 4. **Accelerate Development Cycles**
- Facilitate efficient and effective testing processes that integrate seamlessly into modern development workflows, helping teams deliver high-quality software faster.

---

**Testrium** is your go-to framework for advanced testing with probes and dynamic validation. Elevate your testing strategy with **Testrium** and enhance your development process with robust, adaptable testing capabilities.
