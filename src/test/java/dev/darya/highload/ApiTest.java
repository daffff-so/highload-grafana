package dev.darya.highload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.http.MediaType.APPLICATION_JSON;

@SpringBootTest
@AutoConfigureMockMvc
class ApiTest {
    @Autowired MockMvc mvc;

    @Test void healthIsAvailable() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("UP"));
    }

    @Test void createReadUpdateAndMissingItem() throws Exception {
        String body = mvc.perform(post("/items").contentType(APPLICATION_JSON).content("{\"name\":\"First\"}"))
                .andExpect(status().isCreated()).andExpect(header().exists("Location"))
                .andReturn().getResponse().getContentAsString();
        long id = new com.fasterxml.jackson.databind.ObjectMapper().readTree(body).get("id").asLong();
        mvc.perform(get("/items/" + id)).andExpect(status().isOk()).andExpect(jsonPath("$.name").value("First"));
        mvc.perform(put("/items/" + id).contentType(APPLICATION_JSON).content("{\"name\":\"Second\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.name").value("Second"));
        mvc.perform(get("/items/" + id)).andExpect(jsonPath("$.name").value("Second"));
        mvc.perform(get("/items/999999999")).andExpect(status().isNotFound());
        mvc.perform(put("/items/999999999").contentType(APPLICATION_JSON).content("{\"name\":\"X\"}"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/items/999999999")).andExpect(status().isNotFound());
    }

    @Test void rejectsInvalidRequests() throws Exception {
        for (String body : new String[]{"{}", "{\"name\":\" \"}", "not-json"}) {
            mvc.perform(post("/items").contentType(APPLICATION_JSON).content(body)).andExpect(status().isBadRequest());
        }
        mvc.perform(get("/items/not-a-number")).andExpect(status().isBadRequest());
    }
}
